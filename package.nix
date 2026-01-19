{
  lib,
  stdenv,
  python3,
  pkg-config,
  glib,
  packagekit,
  nix,
  nix-search-cli,
  packagekitSrc,
}:
let
  backendName = "nix-profile";

  # Python backend as a proper Python application
  pythonBackend = python3.pkgs.buildPythonApplication {
    pname = "packagekit-nix-profile-backend";
    version = "1.0.0";
    pyproject = true;

    src = lib.cleanSourceWith {
      src = ./.;
      filter =
        path: type:
        let
          baseName = baseNameOf path;
        in
        baseName != ".git" && baseName != "result" && baseName != "__pycache__";
    };

    build-system = [ python3.pkgs.setuptools ];

    dependencies = with python3.pkgs; [
      (toPythonModule packagekit)
    ];

    makeWrapperArgs = [
      "--prefix"
      "PATH"
      ":"
      "${lib.makeBinPath [
        nix
        nix-search-cli
      ]}"
    ];

    meta.mainProgram = "nix_profile_backend";
  };

  # C shim library
  cBackend = stdenv.mkDerivation {
    pname = "packagekit-backend-nix-profile-shim";
    version = "1.0.0";

    src = lib.cleanSourceWith {
      src = ./.;
      filter = path: type: (baseNameOf path) == "pk-backend-nix-profile.c";
    };

    nativeBuildInputs = [ pkg-config ];
    buildInputs = [
      glib
      packagekit
    ];

    buildPhase = ''
      ${stdenv.cc}/bin/cc -shared -fPIC \
        $(pkg-config --cflags glib-2.0 packagekit-glib2) \
        -I${packagekitSrc}/src \
        -I${packagekitSrc}/lib/packagekit-glib2 \
        -DPK_COMPILATION \
        -DG_LOG_DOMAIN=\"PackageKit-Backend-nix-profile\" \
        -o libpk_backend_nix-profile.so \
        pk-backend-nix-profile.c \
        $(pkg-config --libs glib-2.0 packagekit-glib2)
    '';

    installPhase = ''
      mkdir -p $out/lib/packagekit-backend
      cp libpk_backend_nix-profile.so $out/lib/packagekit-backend/
    '';

    dontStrip = true;
  };
in
stdenv.mkDerivation {
  pname = "packagekit-backend-nix-profile";
  version = "1.0.0";

  dontUnpack = true;

  installPhase = ''
    mkdir -p $out/lib/packagekit-backend
    mkdir -p $out/share/PackageKit/helpers/${backendName}

    # Link C backend
    ln -s ${cBackend}/lib/packagekit-backend/*.so $out/lib/packagekit-backend/

    # Link Python backend (the wrapped executable)
    ln -s ${pythonBackend}/bin/nix_profile_backend $out/share/PackageKit/helpers/${backendName}/nix_profile_backend.py
  '';

  meta = with lib; {
    description = "PackageKit backend for Nix profile management";
    license = licenses.gpl2Plus;
    platforms = platforms.linux;
  };
}
