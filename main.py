import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from answer import main as answer_main
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

    ask_parser = subparsers.add_parser("ask", help="Generate a grounded PQL answer.")
    ask_parser.add_argument("question", help="Natural-language PQL request.")
    ask_parser.add_argument("-k", "--top-k", type=int, default=5, help="Number of chunks to retrieve.")
    ask_parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI chat model to use.")
    ask_parser.add_argument("--schema", help="Inline table/column schema context.")
    ask_parser.add_argument("--schema-file", help="Path to a file containing table/column schema context.")
    ask_parser.add_argument("--session-id", help="Optional session ID to store in the query log.")
    ask_parser.add_argument(
        "--log-path",
        default="data/logs/queries.jsonl",
        help="JSONL log path. Use an empty string to disable logging.",
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

    if args.command == "ask":
        argv = [
            args.question,
            "--top-k",
            str(args.top_k),
            "--model",
            args.model,
            "--log-path",
            args.log_path,
        ]
        if args.schema:
            argv.extend(["--schema", args.schema])
        if args.schema_file:
            argv.extend(["--schema-file", args.schema_file])
        if args.session_id:
            argv.extend(["--session-id", args.session_id])
        return answer_main(argv)

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
