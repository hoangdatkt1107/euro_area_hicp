import argparse
import json
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

def cmd_backtest(args):
    from src.forecast import backtest
    out = backtest.build(ablations=not args.no_ablations, workers=args.workers)
    print(f"  {out.variant.nunique()} runs, {out.origin.nunique()} origins, {len(out):,} rows")
    print(f"saved: {settings.gold / 'backtest.parquet'}")
    return 0

def cmd_evaluate(args):
    from src.forecast import evaluate
    if not (settings.gold / "backtest.parquet").exists():
        print("no backtest yet, run `backtest` first")
        return 1
    path = evaluate.write()
    ev = json.loads((settings.gold / "evaluation.json").read_text())
    print("  avg RMSE: " + ", ".join(f"{settings.label(m)} {v:.3f}" for m, v in ev["avg_rmse"].items()))
    print(f"  chosen: {settings.label(ev['selected'])}")
    print(f"report: {path}")
    return 0

def cmd_forecast(args):
    from src.forecast import live
    if not (settings.gold / "evaluation.json").exists():
        print("no model chosen yet, run `evaluate` first")
        return 1
    r = live.run()
    print(f"  {settings.label(r['model'])}, made as of {r['made']} with HICP to {r['last_hicp']}")
    for f in r["forecast"]:
        print(f"  {f['month']}  {f['yoy']:.2f}%  (90%: {f['q05']:.2f} to {f['q95']:.2f})")
    for name, s in r["scenarios"].items():
        print(f"  {name:<20} " + "  ".join(f"{v:.2f}" for v in s["yoy"]))
    print(f"report: {settings.reports / 'forecast.md'}")
    return 0

def cmd_passthrough(args):
    from src.shocks import passthrough
    est = passthrough.write()
    for g in ("FUEL", "ELC_GAS", "TOTAL"):
        print(f"  Brent +1%, after a year: {settings.label(g)} {est['brent'][g].elasticity[12]:+.3f}%")
    print(f"report: {settings.reports / 'passthrough.md'}")
    return 0

def cmd_shocks(args):
    from src.shocks import presets
    if not (settings.gold / "passthrough.json").exists():
        print("no pass-through yet, run `passthrough` first")
        return 1
    saved = presets.write()
    months = json.loads((settings.gold / "presets.json").read_text())["months"]
    year = str(int(months[-1][:4]) - 1)
    for p in saved:
        avg = [v for m, v in zip(months, p["results"]["impact"], strict=True) if m.startswith(year)]
        print(f"  {p['name']:<34} {year} avg {sum(avg) / len(avg):+.2f} pp")
    print(f"report: {settings.reports / 'shocks.md'}")
    return 0

def cmd_all(args):
    # stop before modelling if the data or the gates fail
    for step in (cmd_data, cmd_validate):
        if step(args):
            print(f"stopped: {step.__name__[4:]} failed")
            return 1
    for step in (cmd_qa, cmd_backtest, cmd_evaluate, cmd_forecast, cmd_passthrough, cmd_shocks):
        if step(args):
            return 1
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
    data.set_defaults(func=cmd_data)
    validate = sub.add_parser("validate", help="rebuild official aggregates and run the gates")
    validate.set_defaults(func=cmd_validate)
    sub.add_parser("qa", help="write reports/qa_findings.md").set_defaults(func=cmd_qa)
    backtest = sub.add_parser("backtest", help="real-time backtest of every model")
    backtest.set_defaults(func=cmd_backtest)
    sub.add_parser("evaluate", help="score the backtest and pick the model").set_defaults(func=cmd_evaluate)
    sub.add_parser("forecast", help="forecast the next three months").set_defaults(func=cmd_forecast)
    sub.add_parser("passthrough", help="how oil, gas and energy pass through to the groups").set_defaults(
        func=cmd_passthrough)
    sub.add_parser("shocks", help="run the shock presets").set_defaults(func=cmd_shocks)
    everything = sub.add_parser("all", help="everything above, in order")
    everything.set_defaults(func=cmd_all)

    for p in (data, everything):
        p.add_argument("--refresh", action="store_true", help="ignore today's cached raw files")
        p.add_argument("--no-external", action="store_true", help="Eurostat only")
    for p in (backtest, everything):
        p.add_argument("--no-ablations", action="store_true", help="skip the runs without each source")
        p.add_argument("--workers", type=int, help="processes for the backtest, default all cores")

    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
