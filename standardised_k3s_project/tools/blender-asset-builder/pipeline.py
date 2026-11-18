#!/usr/bin/env python3
"""Production request entry point."""
import sys

def main():
 if '--request' not in sys.argv:
  print('BLOCKED: legacy pipeline retired; use --request with the production native builder')
  return 2
 from request_pipeline import main as request_main
 return request_main()

if __name__=='__main__':sys.exit(main())
