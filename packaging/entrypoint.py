"""PyInstaller entry point; worker mode must precede application startup."""
import multiprocessing
import sys

from zhenxia.runtime import configure_runtime

if __name__ == '__main__':
    multiprocessing.freeze_support()
    configure_runtime()
    if sys.argv[1:] == ['--ytdlp-worker']:
        from zhenxia.ytdlp_worker import main
    elif sys.argv[1:] == ['--self-check']:
        from zhenxia.runtime import check_runtime as main
    else:
        from zhenxia.__main__ import main
    main()
