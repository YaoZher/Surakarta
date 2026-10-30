"""Export the standalone server from the shared rule source, without GUI assets."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def export(destination: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects a previously exported deployment artifact.
    with ZipFile(destination, "x", compression=ZIP_DEFLATED) as archive:
        for path in sorted((root / "engine").glob("*.py")):
            archive.write(path, path.relative_to(root).as_posix())
        for relative in ("networking/__init__.py", "networking/server.py",
                         "server/__init__.py", "server/__main__.py", "server/requirements.txt",
                         "server/Dockerfile", "server/README.md", "VERSION.json", "NETWORK_CONTRACT.md"):
            archive.write(root / relative, relative)
        archive.write(root / "server/requirements.txt", "requirements.txt")
        archive.writestr("README.md", "# Surakarta 独立房间服务器\n\n"
                         "Python 3.10+。在本目录运行：\n\n"
                         "```sh\npython -m pip install -r requirements.txt\n"
                         "python -m server --host 0.0.0.0 --port 8765\n```\n\n"
                         "部署与房间规则详见 server/README.md。\n"
                         "此包由游戏仓库共享源码导出；修改应在原仓库维护后重新导出。\n")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/Surakarta_Server.zip"))
    args = parser.parse_args()
    print(export(args.output))


if __name__ == "__main__":
    main()
