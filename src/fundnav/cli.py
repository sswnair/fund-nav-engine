"""Command line interface.

    fundnav run --sample                 the sample fund, Q4 2025, all outputs
    fundnav run --data path/to/fund      a fund folder of your own
    fundnav fx --start 2025-10-01 --end 2025-12-31 --currencies USD GBP CHF

Run any command with --help for its options.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import sys

from . import __version__
from .data import SAMPLE_DIR, download_fx, load_fund
from .engine import run
from .report import fmt_date, money, plural, write_outputs

EXIT_OK, EXIT_ERROR, EXIT_BREAKS = 0, 1, 2


def _date(text: str) -> dt.date:
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"dates look like 2025-12-31, got {text!r}") from None


def cmd_run(args) -> int:
    if not args.sample and not args.data:
        print("Choose a fund: --sample, or --data with the path to a fund folder.", file=sys.stderr)
        return EXIT_ERROR
    folder = SAMPLE_DIR if args.sample else args.data
    result = run(load_fund(folder), args.start, args.end)
    last = result.last
    config = result.data.config

    print(f"\n{config.name} · {fmt_date(result.days[0].date)} to {fmt_date(last.date)} · {len(result.days)} valuation days")
    print(f"  Net assets {config.base_currency} {money(last.net_assets)}")
    for sc in config.share_classes:
        v = last.valuations[sc.code]
        print(f"  {sc.code:<8} NAV per share {sc.currency} {v.nav_per_share:,.4f}   units {last.states[sc.code].units:,.3f}")
    out_of_proof = [d.date for d in result.days if abs(d.proof) >= 0.005]
    print("  NAV proof: ties on every day" if not out_of_proof else f"  NAV proof: out on {len(out_of_proof)} days, first {out_of_proof[0]}")
    register = last.register
    open_rows = register[register["status"] == "open"] if not register.empty else register
    print(f"  {plural(len(open_rows), 'open break', 'open breaks')}", end="")
    print(f", oldest {int(open_rows['age'].max())} business days" if not open_rows.empty else "")
    for _, r in open_rows.iterrows():
        print(f"    {r['age']:>3}d  {r['category']:<8} {r['reference']:<14} {r['detail']}")

    paths = write_outputs(result, args.out, sample=args.sample)
    print(f"\nNAV pack: {paths['report']}")
    print(f"CSV files in {pathlib.Path(args.out)}")
    if args.fail_on_breaks and (out_of_proof or not open_rows.empty):
        return EXIT_BREAKS
    return EXIT_OK


def cmd_fx(args) -> int:
    rates = download_fx(args.currencies, args.start, args.end)
    rates.to_csv(args.out, index=False)
    print(f"{len(rates)} rates from {fmt_date(args.start)} to {fmt_date(args.end)} written to {args.out}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fundnav", description="Daily NAV calculation and reconciliation for a multi-class fund.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("run", help="value the fund day by day and reconcile it")
    p.add_argument("--sample", action="store_true", help="the synthetic sample fund in data/sample")
    p.add_argument("--data", type=pathlib.Path, help="a folder holding a fund's input files")
    p.add_argument("--start", type=_date, help="first valuation day (default: the day after the opening date)")
    p.add_argument("--end", type=_date, help="last valuation day (default: the last day with prices)")
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("output"), help="folder for the outputs (default: output)")
    p.add_argument("--fail-on-breaks", action="store_true", help=f"exit with code {EXIT_BREAKS} if a break is open or the proof fails")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("fx", help="download ECB euro reference rates")
    p.add_argument("--start", type=_date, required=True)
    p.add_argument("--end", type=_date, required=True)
    p.add_argument("--currencies", nargs="+", default=["USD", "GBP", "CHF"])
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("fx.csv"))
    p.set_defaults(func=cmd_fx)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return EXIT_OK
    except OSError as exc:
        if type(exc).__module__.startswith("requests") or isinstance(exc, (ConnectionError, TimeoutError)):
            print(f"\nCould not download the rates: {exc}", file=sys.stderr)
        else:
            print(f"\nError: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
