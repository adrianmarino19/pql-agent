import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from retrieve import main as retrieve_main


def main() -> int:
    parser = argparse.ArgumentParser(description="PQL Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    retrieve_parser = subparsers.add_parser("retrieve", help="Retrieve relevant PQL docs chunks.")
    retrieve_parser.add_argument("query", help="Natural-language query or PQL term.")
    retrieve_parser.add_argument("-k", "--top-k", type=int, default=5, help="Number of chunks to print.")
    retrieve_parser.add_argument(
        "--max-chars",
        type=int,
        default=800,
        help="Maximum characters of chunk text to print per result.",
    )

    args = parser.parse_args()

    if args.command == "retrieve":
        return retrieve_main(
            [
                args.query,
                "--top-k",
                str(args.top_k),
                "--max-chars",
                str(args.max_chars),
            ]
        )

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
