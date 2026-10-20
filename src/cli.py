import argparse
import sys
from loguru import logger
from src.config import settings
import argparse
import sys
from loguru import logger
from src.config import settings

# modules are imported inside each command, so `hicp --help` stays quick and
# `hicp data` never loads matplotlib

def cmd_data(args):
    from src import report, silver
    result = silver.build(refresh=args.refresh, with_external=not args.no_external)
    path = report.write()
    for c in result["checks"]:
        print(f"  {'ok  ' if c['ok'] else 'FAIL'} [{c['layer']}] {c['check']}: {c['detail']}")
    print(f"report: {path}")
    # only Eurostat can fail the run, the external sources are optional
    return int(any(not c["ok"] and c["layer"] == "eurostat" for c in result["checks"]))

def cmd_validate(args):
    from src import validate
    result = validate.run()
    for g in result["gates"]:
        if "max_abs_pp" in g:
            detail = f"max gap {g['max_abs_pp']:.3f} pp over {g['months']} months"
        else:
            detail = g.get("detail", "")
        print(f"  {'ok  ' if g['ok'] else 'FAIL'} {g['id']:<4} {g['name']}: {detail}")
    # first entry is Eurostat itself, already shown as V5
    for f in result["freshness"][1:]:
        print(f"  {'ok  ' if f['ok'] else 'warn'} fresh {f['source']}: {f['latest']} ({f['rule']})")
    return int(not all(g["ok"] for g in result["gates"]))

def cmd_qa(args):
    from src import qa

    print(f"report: {qa.write()}")
    return 0

def setup_logging(verbose=False):
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO",
               format="<green>{time:HH:mm:ss}</green> <level>{level:<7}</level> {name}: {message}")
    # full debug log of every run, one file a week, kept for a month
    logger.add(settings.logs / "hicp_{time:YYYY-MM-DD}.log", level="DEBUG",
               rotation="1 week", retention="1 month")

def main(argv=None):
    parser = argparse.ArgumentParser(prog="hicp", description="Euro area HICP pipeline")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    data = sub.add_parser("data", help="download sources, build silver tables, run checks")
    data.add_argument("--refresh", action="store_true", help="ignore today's cached raw files")
    data.add_argument("--no-external", action="store_true", help="Eurostat only")
    data.set_defaults(func=cmd_data)
    validate = sub.add_parser("validate", help="rebuild official aggregates and run the gates")
    validate.set_defaults(func=cmd_validate)
    sub.add_parser("qa", help="write reports/qa_findings.md").set_defaults(func=cmd_qa)

    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
