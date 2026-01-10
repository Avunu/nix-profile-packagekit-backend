{
  lib,
  stdenv,
  python3,
  pkg-config,
  glib,
  packagekit,
  nix,
  packagekitSrc,
}:

let
  # Python environment with dependencies
  pythonEnv = python3.withPackages (
    ps: with ps; [
      brotli    # For decompressing nix-data-db
      requests  # For downloading data at runtime
    ]
  );

  backendName = "nix-profile";

in
stdenv.mkDerivation {
  pname = "packagekit-backend-nix-profile";
  version = "1.0.0";

  src = lib.cleanSourceWith {
    src = ./.;
    filter =
      path: type:
      let
        baseName = baseNameOf path;
      in
      # Exclude git, build artifacts, data directories
      baseName != ".git"
      && baseName != "result"
      && baseName != "flake.lock"
      && baseName != "__pycache__"
      && baseName != ".pytest_cache"
      && baseName != "nix-data-db"
      && baseName != "nixos-appstream-data"
      && true;
  };

  nativeBuildInputs = [
    pkg-config
    python3 # For generating enums.py
  ];

  buildInputs = [
    glib
    packagekit
  ];

  # Build the C shim that spawns the Python backend
  buildPhase = ''
    runHook preBuild

    # Compile the C backend shim
    ${stdenv.cc}/bin/cc -shared -fPIC \
      $(pkg-config --cflags glib-2.0 packagekit-glib2) \
      -I${packagekitSrc}/src \
      -I${packagekitSrc}/lib/packagekit-glib2 \
      -DPK_COMPILATION \
      -DG_LOG_DOMAIN=\"PackageKit-Backend-nix-profile\" \
      -o libpk_backend_nix-profile.so \
      pk-backend-nix-profile.c \
      $(pkg-config --libs glib-2.0 packagekit-glib2)

    # Generate enums.py from PackageKit source
    python3 ${packagekitSrc}/lib/python/enum-convertor.py \
      ${packagekitSrc}/lib/packagekit-glib2/pk-enum.c > enums.py

    runHook postBuild
  '';

  installPhase = ''
        runHook preInstall
        
        # Install the backend shared library
        mkdir -p $out/lib/packagekit-backend
        cp libpk_backend_nix-profile.so $out/lib/packagekit-backend/
        
        # Install Python backend to helpers directory
        mkdir -p $out/share/PackageKit/helpers/${backendName}
        
        # Create wrapper script that sets PYTHONPATH and runs backend
        cat > $out/share/PackageKit/helpers/${backendName}/nix_profile_backend.py << EOF
    #!/bin/sh
    export PYTHONPATH="$out/share/PackageKit/helpers/${backendName}:\$PYTHONPATH"
    exec ${pythonEnv}/bin/python3 $out/share/PackageKit/helpers/${backendName}/nix_profile_backend.py.real "\$@"
    EOF
        chmod +x $out/share/PackageKit/helpers/${backendName}/nix_profile_backend.py
        
        # Install actual Python backend and modules
        cp nix_profile_backend.py $out/share/PackageKit/helpers/${backendName}/nix_profile_backend.py.real
        cp nix_profile.py $out/share/PackageKit/helpers/${backendName}/
        cp nix_search.py $out/share/PackageKit/helpers/${backendName}/
        
        # Install PackageKit Python library from upstream source
        mkdir -p $out/share/PackageKit/helpers/${backendName}/packagekit
        cp ${packagekitSrc}/lib/python/packagekit/*.py $out/share/PackageKit/helpers/${backendName}/packagekit/
        cp enums.py $out/share/PackageKit/helpers/${backendName}/packagekit/
        
        runHook postInstall
  '';

  dontStrip = true;

  meta = with lib; {
    description = "PackageKit backend for Nix profile management";
    longDescription = ''
      A Python-based PackageKit backend that enables software centers
      (GNOME Software, KDE Discover) to manage packages in the user's
      Nix profile via 'nix profile' commands.
    '';
    license = licenses.gpl2Plus;
    platforms = platforms.linux;
  };
}
