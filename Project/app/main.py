from __future__ import annotations

import argparse
from pathlib import Path

from app.pipeline import Edu2WorkPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="Edu2WorkAI",
        description="Analyze education and work reports to generate AI idea cards.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root path (default: current working directory)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create workspace and seed prompt/schema files")
    subparsers.add_parser("process-education", help="Process education materials")
    subparsers.add_parser("transcribe-audio", help="Transcribe education audio files")
    subparsers.add_parser("extract-ppt", help="Extract PPT/PPTX education slides")
    subparsers.add_parser("convert-docs", help="Convert HWPX/HWP documents into Markdown extracts")
    subparsers.add_parser("process-reports", help="Process report materials")
    subparsers.add_parser("build-map", help="Build department work map")
    subparsers.add_parser("generate-ideas", help="Generate AI idea cards")
    subparsers.add_parser("export", help="Export final report drafts")
    subparsers.add_parser("run-all", help="Run the full Edu2WorkAI pipeline")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    pipeline = Edu2WorkPipeline(project_root=args.project_root)

    if args.command == "init":
        pipeline.init()
    elif args.command == "process-education":
        pipeline.process_education()
    elif args.command == "transcribe-audio":
        pipeline.transcribe_audio()
    elif args.command == "extract-ppt":
        pipeline.extract_ppt()
    elif args.command == "convert-docs":
        pipeline.convert_docs()
    elif args.command == "process-reports":
        pipeline.process_reports()
    elif args.command == "build-map":
        pipeline.build_map()
    elif args.command == "generate-ideas":
        pipeline.generate_ideas()
    elif args.command == "export":
        pipeline.export()
    elif args.command == "run-all":
        pipeline.run_all()


if __name__ == "__main__":
    main()
