{ lib
, stdenv
, python3
, pkg-config
, glib
, packagekit
, nix-data-db
, nixos-appstream-data
}:

let
  # Python environment with dependencies
  pythonEnv = python3.withPackages (ps: with ps; [
    brotli
  ]);
  
  backendName = "nix-profile";
  
in stdenv.mkDerivation {
  pname = "packagekit-backend-nix-profile";
  version = "1.0.0";

  # Use filterSource instead of builtins.path for better control
  src = lib.cleanSourceWith {
    src = ./.;
    filter = path: type:
      let
        baseName = baseNameOf path;
        relativePath = lib.removePrefix (toString ./. + "/") (toString path);
      in
        # Exclude git, build artifacts, etc.
        baseName != ".git" &&
        baseName != "result" &&
        baseName != "flake.lock" &&
        baseName != "__pycache__" &&
        baseName != ".pytest_cache" &&
        # Exclude large data directories (they're passed as inputs)
        baseName != "nix-data-db" &&
        baseName != "nixos-appstream-data" &&
        baseName != "nix-data-generator" &&
        baseName != "nixos-appstream-generator" &&
        baseName != "nixpkgs-version-data" &&
        # Include everything else
        true;
  };
  
  nativeBuildInputs = [
    pkg-config
  ];
  
  buildInputs = [
    glib
    packagekit
  ];
  
  # Build the C shim that spawns the Python backend
  buildPhase = ''
    runHook preBuild
    
    # Compile the C backend shim
    # This creates libpk_backend_nix-profile.so
    ${stdenv.cc}/bin/cc -shared -fPIC \
      $(pkg-config --cflags glib-2.0 packagekit-glib2) \
      -I${packagekit}/include/PackageKit/backend \
      -DG_LOG_DOMAIN=\"PackageKit-Backend-nix-profile\" \
      -o libpk_backend_nix-profile.so \
      pk-backend-nix-profile.c \
      $(pkg-config --libs glib-2.0 packagekit-glib2)
    
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
    cat > $out/share/PackageKit/helpers/${backendName}/nixProfileBackend.py << EOF
#!/bin/sh
export PYTHONPATH="$out/share/PackageKit/helpers/${backendName}:\$PYTHONPATH"
exec ${pythonEnv}/bin/python3 $out/share/PackageKit/helpers/${backendName}/nixProfileBackend.py.real "\$@"
EOF
    chmod +x $out/share/PackageKit/helpers/${backendName}/nixProfileBackend.py
    
    # Install actual Python backend and modules
    cp nixProfileBackend.py $out/share/PackageKit/helpers/${backendName}/nixProfileBackend.py.real
    cp nix_profile.py $out/share/PackageKit/helpers/${backendName}/
    cp nixpkgs_appdata.py $out/share/PackageKit/helpers/${backendName}/
    cp appstream_parser.py $out/share/PackageKit/helpers/${backendName}/
    
    # Install PackageKit Python library from source
    cp -r packagekit $out/share/PackageKit/helpers/${backendName}/
    
    # Link data repositories
    ln -s ${nix-data-db} $out/share/PackageKit/helpers/${backendName}/nix-data-db
    ln -s ${nixos-appstream-data} $out/share/PackageKit/helpers/${backendName}/nixos-appstream-data
    
    runHook postInstall
  '';
  
  dontStrip = true;

  meta = with lib; {
    description = "PackageKit backend for Nix profile management";
    longDescription = ''
      A Python-based PackageKit backend that enables software centers
      (GNOME Software, KDE Discover) to manage packages in the user's
      Nix profile via 'nix profile' commands.
      
      Features:
      - Browse nixpkgs with rich metadata from snowfallorg
      - Install/remove/update packages in user profile
      - Search by name, description, or category
      - No root required - user-level operations only
    '';
    license = licenses.gpl2Plus;
    platforms = platforms.linux;
  };
}
