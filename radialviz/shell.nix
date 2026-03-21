{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [
    pkgs.wget
    (pkgs.python3.withPackages (ps: with ps; [
      flask
      openai
      pydub
      flask-cors
    ]))
  ];
}
