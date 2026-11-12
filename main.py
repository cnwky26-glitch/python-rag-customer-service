"""运行方式见 README.md。"""
import argparse
import json

from kb.core import ROOT, Retriever, build, load_config, load_model
from kb.prepare import prepare


def main():
    parser = argparse.ArgumentParser(description="Python 官方文档客服知识库")
    parser.add_argument("--config", help="TOML 配置路径")
    commands = parser.add_subparsers(dest="command", required=True)
    data = commands.add_parser("prepare", help="从官方 HTML 提取知识条目")
    data.add_argument("--download", action="store_true", help="联网刷新原始 HTML")
    commands.add_parser("build", help="批量向量化并重建当前配置指定的表")
    query = commands.add_parser("query", help="检索并返回来源证据")
    query.add_argument("question")
    query.add_argument("--module")
    query.add_argument("--version")
    query.add_argument("--mode", choices=["vector", "hybrid"], default="hybrid")
    query.add_argument("--threshold", type=float)
    query.add_argument("--top-k", type=int)
    commands.add_parser("evaluate", help="运行要求的评估和对比实验")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "prepare":
        result = prepare(ROOT, config, args.download)
    else:
        model = load_model(config)
        if args.command == "build":
            result = build(config, model)
        elif args.command == "query":
            result = Retriever(config, model).search(args.question, args.module, args.version,
                                                    args.mode, args.threshold, args.top_k)
        else:
            from kb.evaluate import evaluate
            result = evaluate(config, model)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
