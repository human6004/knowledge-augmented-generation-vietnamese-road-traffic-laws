"""One official CLI; orchestration and verification remain library calls."""
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description='KAG scoped builder and read-only verification')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('run', 'resume', 'verify'):
        command = commands.add_parser(name)
        command.add_argument('--config', required=True)
        command.add_argument('--run-id', required=True)
    args = parser.parse_args(argv)
    from kag import runner
    from kag.run_state import RunBlocked, MESSAGES
    try:
        config = runner.load_config(args.config)
        if args.command == 'verify':
            code = runner.verify_run(config, run_id=args.run_id)
        else:
            code = runner.run(config, run_id=args.run_id, resume=args.command == 'resume')
    except RunBlocked as error:
        print('BLOCKED: ' + str(error), file=sys.stderr)
        return 2
    except Exception:
        print('ERROR: ' + MESSAGES['RUNTIME'], file=sys.stderr)
        return 1
    print({0: 'PASS', 1: 'ERROR', 2: 'BLOCKED'}[code])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
