"""Offline / scheduled AgentOps workflows. Does not modify any external account."""
from __future__ import annotations
import argparse
import json
import sys
import time
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path
from . import engine, store


def fetch_csv(url: str) -> bytes:
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.netloc or parts.username or parts.password:
        raise ValueError('Only unauthenticated HTTPS CSV URLs are accepted')
    # Explicit operator CLI action; never called via public web API.
    req=urllib.request.Request(url,headers={'User-Agent':'AgentOpsStudio/2.0'})
    with urllib.request.urlopen(req,timeout=20) as response:
        if response.geturl().split(':',1)[0]!='https':
            raise ValueError('Redirects to non-HTTPS are not allowed')
        raw=response.read(1_048_577)
    if len(raw)>1_048_576:
        raise ValueError('Maximum CSV size is 1MB')
    return raw


def run_workflows(force: bool=False):
    result=[]
    for slug in ('voc','ads','kol','brief'):
        r=engine.execute(slug,force=force)
        result.append({'workflow':slug,'status':r['status'],'run_id':r['run_id'],
                       'approvals_created':r['approvals_created']})
    print(json.dumps(result,indent=2,ensure_ascii=False))


def main(argv=None):
    parser=argparse.ArgumentParser(description='AgentOps data ingestion and scheduled local analysis')
    sub=parser.add_subparsers(dest='cmd',required=True)
    imp=sub.add_parser('import-csv',help='Import real, validated UTF-8 CSV records')
    imp.add_argument('dataset',choices=sorted(store.VALID_TABLES));imp.add_argument('file',type=Path)
    remote=sub.add_parser('fetch-csv',help='Fetch an operator-provided public HTTPS CSV')
    remote.add_argument('dataset',choices=sorted(store.VALID_TABLES));remote.add_argument('url')
    run=sub.add_parser('run',help='Run all workflows once or at a periodic interval')
    run.add_argument('--every',type=int,default=0,help='seconds between cycles; 0 = once')
    run.add_argument('--force',action='store_true',help='bypass input-hash cache')
    args=parser.parse_args(argv)
    store.initialize()
    try:
        if args.cmd=='import-csv':
            print(json.dumps(store.import_csv(args.dataset,args.file.read_bytes()),ensure_ascii=False))
        elif args.cmd=='fetch-csv':
            print(json.dumps(store.import_csv(args.dataset,fetch_csv(args.url)),ensure_ascii=False))
        elif args.cmd=='run':
            if args.every and args.every<60:
                parser.error('For recurring tasks, --every must be at least 60 seconds')
            while True:
                run_workflows(force=args.force)
                if not args.every: break
                time.sleep(args.every)
    except (ValueError,OSError) as e:
        print(f'error: {e}',file=sys.stderr);return 1
    except KeyboardInterrupt:
        return 0
    return 0

if __name__=='__main__':
    raise SystemExit(main())
