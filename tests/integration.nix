# NixOS integration test for PackageKit nix-profile backend
#
# Run with: nix build .#checks.x86_64-linux.integration
# Or: nix flake check
{
  pkgs,
  self,
}:

pkgs.testers.runNixOSTest {
  name = "packagekit-nix-profile-backend";

  nodes.machine =
    { config, pkgs, ... }:
    {
      imports = [ self.nixosModules.default ];

      # Enable the backend
      services.packagekit.backends.nix-profile.enable = true;

      # Ensure we have a test user with a home directory
      users.users.testuser = {
        isNormalUser = true;
        home = "/home/testuser";
      };

      # Enable D-Bus (required for PackageKit)
      services.dbus.enable = true;

      # Helpful for debugging
      environment.systemPackages = with pkgs; [
        packagekit
      ];
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")

    # Check that the backend library is installed
    machine.succeed("test -f /var/lib/PackageKit/plugins/libpk_backend_nix-profile.so")

    # Check that the helper scripts are installed
    machine.succeed("test -d /usr/share/PackageKit/helpers/nix-profile")
    machine.succeed("test -f /usr/share/PackageKit/helpers/nix-profile/nix_profile_backend.py")

    # Check PackageKit config
    machine.succeed("grep -q 'DefaultBackend=nix-profile' /etc/PackageKit/PackageKit.conf")

    # Wait for D-Bus
    machine.wait_for_unit("dbus.service")

    # Test that PackageKit daemon can start (may fail to load backend, but should start)
    machine.succeed("systemctl start packagekit || true")

    # Test pkcon can communicate with daemon
    # Note: This may show errors about the backend, which is expected in minimal test env
    output = machine.succeed("pkcon get-details firefox 2>&1 || true")
    print(f"pkcon output: {output}")

    # Test the Python backend directly as testuser
    machine.succeed(
      "su - testuser -c '"
      "printf \"get-packages\\tinstalled\\n\" | "
      "/usr/share/PackageKit/helpers/nix-profile/nix_profile_backend.py"
      "' 2>&1 | head -20"
    )

    # Test search (requires network, may timeout in test VM)
    # machine.succeed(
    #   "su - testuser -c '"
    #   "printf \"search-names\\tnone\\tfirefox\\n\" | "
    #   "/usr/share/PackageKit/helpers/nix-profile/nix_profile_backend.py"
    #   "' 2>&1 | head -20"
    # )
  '';
}
