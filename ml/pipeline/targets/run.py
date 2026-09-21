import argparse
import os

from pipeline import config, extract, training
from pipeline.targets import discovery_run, modules


def _phase(args):
    events = extract.extract_events(modules.PHASE_SENSOR)
    frame, _, _ = modules.build_phase_frame(events, horizons=(args.horizon,), sustained_minutes=args.sustained_minutes)
    target = f"{args.target}_y{args.horizon}"
    report = modules.train_and_report(frame, target, training.feature_columns(), args.train_end, args.valid_year,
                                      args.out, f"phase_{target}")
    print({k: round(v, 4) if isinstance(v, float) else v for k, v in report.items()})


def _alarm(args):
    frame = modules.build_alarm_frame()
    target = f"c{args.window}_corroborated"
    report = modules.train_and_report(frame, target, modules.alarm_feature_columns(frame), args.train_end,
                                      args.valid_year, args.out, f"alarm_{target}")
    print({k: round(v, 4) if isinstance(v, float) else v for k, v in report.items()})


def main():
    parser = argparse.ArgumentParser(prog="pipeline.targets.run")
    sub = parser.add_subparsers(dest="command", required=True)
    disc = sub.add_parser("discovery")
    disc.add_argument("--out", default=config.TABLES_DIR)
    phase = sub.add_parser("phase")
    phase.add_argument("--target", choices=["any", "sustained"], default="any")
    phase.add_argument("--horizon", type=int, default=24)
    phase.add_argument("--sustained-minutes", type=int, default=30)
    phase.add_argument("--train-end", type=int, default=2024)
    phase.add_argument("--valid-year", type=int, default=2025)
    phase.add_argument("--out", default=os.path.join(config.ROOT, "artifacts", "experimental"))
    al = sub.add_parser("alarm")
    al.add_argument("--window", type=int, choices=[15, 30, 60], default=30)
    al.add_argument("--train-end", type=int, default=2024)
    al.add_argument("--valid-year", type=int, default=2025)
    al.add_argument("--out", default=os.path.join(config.ROOT, "artifacts", "experimental"))
    args = parser.parse_args()
    if args.command == "discovery":
        discovery_run.build(args.out)
    elif args.command == "phase":
        _phase(args)
    else:
        _alarm(args)


if __name__ == "__main__":
    main()
