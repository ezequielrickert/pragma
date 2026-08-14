import time
import subprocess
import json

# Simple harness: run the CLI and measure elapsed time
def run(url):
    start = time.time()
    proc = subprocess.run(['python', 'cli.py', '--url', url], capture_output=True, text=True)
    elapsed = time.time() - start
    return {'url': url, 'returncode': proc.returncode, 'elapsed': elapsed, 'stdout': proc.stdout, 'stderr': proc.stderr}

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: python benchmarks/run_benchmark.py <url>')
        sys.exit(1)
    res = run(sys.argv[1])
    print(json.dumps(res, indent=2))
