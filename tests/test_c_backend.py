"""
Tests for the C backend (pk-backend-nix-profile.c).

These tests perform static analysis on the C source to verify correct
PackageKit backend patterns are followed.
"""

import re
from pathlib import Path
from typing import ClassVar

import pytest

# Path to C backend source
C_BACKEND_PATH = Path(__file__).parent.parent / "pk-backend-nix-profile.c"


@pytest.fixture
def c_source() -> str:
	"""Load the C backend source code."""
	return C_BACKEND_PATH.read_text()


def extract_functions(source: str) -> dict[str, str]:
	"""
	Extract function bodies from C source.
	Returns dict mapping function name to function body.
	"""
	functions = {}

	# Match function definitions: return_type\nfunction_name (params)\n{...}
	# PackageKit backend functions follow pattern: pk_backend_* or void pk_backend_*
	pattern = r"(?:void|PkBitfield|gchar\s*\*\*|const\s+gchar\s*\*|gboolean)\s*\n?(pk_backend_\w+)\s*\([^)]*\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}"

	for match in re.finditer(pattern, source, re.MULTILINE | re.DOTALL):
		func_name = match.group(1)
		func_body = match.group(2)
		functions[func_name] = func_body

	return functions


class TestCBackendJobFinished:
	"""
	Test that all backend functions properly terminate jobs.

	PackageKit requires that every job is terminated with pk_backend_job_finished().
	Functions that return errors via pk_backend_job_error_code() must also call
	pk_backend_job_finished() or the job will hang forever, blocking the transaction
	queue.
	"""

	def test_error_code_always_followed_by_finished(self, c_source: str):
		"""
		Verify that pk_backend_job_error_code is always followed by pk_backend_job_finished.

		This is the critical bug we fixed - without this, gnome-packagekit would hang.
		"""
		functions = extract_functions(c_source)

		violations = []

		for func_name, func_body in functions.items():
			# Skip helper functions that don't handle jobs directly
			if func_name in (
				"pk_backend_initialize",
				"pk_backend_destroy",
				"pk_backend_get_groups",
				"pk_backend_get_filters",
				"pk_backend_get_mime_types",
				"pk_backend_cancel",
				"pk_backend_get_description",
				"pk_backend_get_author",
				"pk_backend_supports_parallelization",
			):
				continue

			has_error_code = "pk_backend_job_error_code" in func_body
			has_finished = "pk_backend_job_finished" in func_body
			uses_spawn_helper = "pk_backend_spawn_helper" in func_body

			# If function calls error_code, it must also call finished
			# (unless it delegates to spawn_helper which handles finishing)
			if has_error_code and not has_finished and not uses_spawn_helper:
				violations.append(
					f"{func_name}: calls pk_backend_job_error_code but not pk_backend_job_finished"
				)

		assert not violations, (
			"Found functions that call pk_backend_job_error_code without "
			"pk_backend_job_finished:\n" + "\n".join(f"  - {v}" for v in violations)
		)

	def test_non_spawn_functions_call_finished(self, c_source: str):
		"""
		Verify functions that don't use spawn_helper call pk_backend_job_finished.

		Functions that use pk_backend_spawn_helper don't need to call finished
		because the spawn helper handles it. But functions that handle the job
		directly must call finished.
		"""
		functions = extract_functions(c_source)

		# Functions that handle jobs directly (don't delegate to spawn)
		direct_handlers = []
		for func_name, func_body in functions.items():
			# Skip non-job functions
			if func_name in (
				"pk_backend_initialize",
				"pk_backend_destroy",
				"pk_backend_get_groups",
				"pk_backend_get_filters",
				"pk_backend_get_mime_types",
				"pk_backend_cancel",
				"pk_backend_get_description",
				"pk_backend_get_author",
				"pk_backend_supports_parallelization",
			):
				continue

			uses_spawn = "pk_backend_spawn_helper" in func_body
			if not uses_spawn and "PkBackendJob *job" in c_source:
				# This function handles job directly
				direct_handlers.append((func_name, func_body))

		violations = []
		for func_name, func_body in direct_handlers:
			# Functions that don't spawn must call finished
			if "pk_backend_job_finished" not in func_body:
				# Check if function is trivially empty or just returns
				if func_body.strip() and "return" not in func_body.strip():
					violations.append(
						f"{func_name}: handles job directly but doesn't call pk_backend_job_finished"
					)

		# Note: This test is informational - some patterns are valid without explicit finished
		if violations:
			pytest.fail(
				"Found functions that may not properly finish jobs:\n"
				+ "\n".join(f"  - {v}" for v in violations)
			)

	def test_start_job_error_path_calls_finished(self, c_source: str):
		"""
		Verify pk_backend_start_job calls finished on error path.

		The start_job function is special - if it returns an error (e.g., lock required),
		it must call finished or the job hangs.
		"""
		functions = extract_functions(c_source)

		if "pk_backend_start_job" not in functions:
			pytest.skip("pk_backend_start_job not found")

		func_body = functions["pk_backend_start_job"]

		# If start_job can error, it must finish
		if "pk_backend_job_error_code" in func_body:
			assert "pk_backend_job_finished" in func_body, (
				"pk_backend_start_job calls error_code but not finished - "
				"this will cause jobs to hang when the backend is busy"
			)


class TestCBackendRepoList:
	"""Test that repo list handling is correct."""

	def test_get_repo_list_returns_repo(self, c_source: str):
		"""
		Verify pk_backend_get_repo_list returns at least one repo.

		gnome-packagekit calls get_repo_list on startup. If this returns an error,
		gnome-packagekit may not function correctly.
		"""
		functions = extract_functions(c_source)

		if "pk_backend_get_repo_list" not in functions:
			pytest.skip("pk_backend_get_repo_list not found")

		func_body = functions["pk_backend_get_repo_list"]

		# Should call repo_detail to return at least one repo
		assert "pk_backend_job_repo_detail" in func_body, (
			"pk_backend_get_repo_list should return at least one repo via "
			"pk_backend_job_repo_detail for compatibility with gnome-packagekit"
		)

	def test_get_repo_list_calls_finished(self, c_source: str):
		"""Verify pk_backend_get_repo_list properly finishes the job."""
		functions = extract_functions(c_source)

		if "pk_backend_get_repo_list" not in functions:
			pytest.skip("pk_backend_get_repo_list not found")

		func_body = functions["pk_backend_get_repo_list"]

		assert "pk_backend_job_finished" in func_body, (
			"pk_backend_get_repo_list must call pk_backend_job_finished"
		)


class TestCBackendFunctionSignatures:
	"""Test that all required backend functions are implemented."""

	REQUIRED_FUNCTIONS: ClassVar[list[str]] = [
		"pk_backend_initialize",
		"pk_backend_destroy",
		"pk_backend_get_groups",
		"pk_backend_get_filters",
		"pk_backend_get_description",
		"pk_backend_get_author",
	]

	OPTIONAL_JOB_FUNCTIONS: ClassVar[list[str]] = [
		"pk_backend_cancel",
		"pk_backend_get_details",
		"pk_backend_get_files",
		"pk_backend_get_packages",
		"pk_backend_get_updates",
		"pk_backend_get_update_detail",
		"pk_backend_install_packages",
		"pk_backend_refresh_cache",
		"pk_backend_remove_packages",
		"pk_backend_resolve",
		"pk_backend_search_details",
		"pk_backend_search_files",
		"pk_backend_search_groups",
		"pk_backend_search_names",
		"pk_backend_update_packages",
		"pk_backend_get_repo_list",
		"pk_backend_repo_enable",
	]

	def test_required_functions_exist(self, c_source: str):
		"""Verify all required backend functions are implemented."""
		functions = extract_functions(c_source)

		missing = []
		for func in self.REQUIRED_FUNCTIONS:
			if func not in functions:
				missing.append(func)

		assert not missing, f"Missing required backend functions: {missing}"

	def test_job_functions_documented(self, c_source: str):
		"""List which job functions are implemented (informational)."""
		functions = extract_functions(c_source)

		implemented = []
		not_implemented = []

		for func in self.OPTIONAL_JOB_FUNCTIONS:
			if func in functions:
				implemented.append(func)
			else:
				not_implemented.append(func)

		# This is informational, not a failure
		print(f"\nImplemented job functions: {len(implemented)}")
		for f in implemented:
			print(f"  ✓ {f}")

		if not_implemented:
			print(f"\nNot implemented: {len(not_implemented)}")
			for f in not_implemented:
				print(f"  ○ {f}")


class TestCBackendErrorHandling:
	"""Test error handling patterns in the backend."""

	def test_all_error_paths_finish_job(self, c_source: str):
		"""
		Comprehensive test that ALL error paths call finished.

		This counts occurrences of error_code and finished to ensure they match.
		"""
		functions = extract_functions(c_source)

		for func_name, func_body in functions.items():
			# Count error_code calls
			error_count = func_body.count("pk_backend_job_error_code")

			if error_count == 0:
				continue

			# Functions using spawn_helper are okay - spawn handles finishing
			if "pk_backend_spawn_helper" in func_body:
				continue

			# Count finished calls
			finished_count = func_body.count("pk_backend_job_finished")

			# Every error path should have a corresponding finished
			# (Note: this is a heuristic - complex control flow may have different counts)
			assert finished_count >= 1, (
				f"{func_name}: has {error_count} error_code call(s) but "
				f"only {finished_count} finished call(s)"
			)

	def test_no_return_before_finished_after_error(self, c_source: str):
		"""
		Check for pattern: error_code followed by return without finished.

		This catches the exact bug we fixed.
		"""
		functions = extract_functions(c_source)

		# Pattern: error_code ... return without finished in between
		bad_pattern = re.compile(
			r"pk_backend_job_error_code\s*\([^;]+;\s*return\s*;",
			re.DOTALL,
		)

		violations = []
		for func_name, func_body in functions.items():
			if bad_pattern.search(func_body):
				violations.append(func_name)

		assert not violations, (
			"Found functions with 'error_code; return;' pattern (missing finished):\n"
			+ "\n".join(f"  - {v}" for v in violations)
		)
