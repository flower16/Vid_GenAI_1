# System packages for the Replit environment (backend + frontend build).
{ pkgs }: {
  deps = [
    pkgs.python312
    pkgs.python312Packages.pip
    pkgs.nodejs_20
    pkgs.bash
  ];
}
