"""Console script for tollan."""
import argparse
import sys


def main(args=None):
    """Console script for tollan."""
    parser = argparse.ArgumentParser(description="Tollan is a utility lib.")
    from .. import _version

    parser.add_argument("--version", "-v", action="version", version=_version.version)
    parser.parse_args(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
