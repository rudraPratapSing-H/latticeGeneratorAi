import os
import tempfile

os.environ["MOCK"] = "1"   # tests run against the canned core; real models need the GPU laptop
os.environ["RUNS_DIR"] = tempfile.mkdtemp(prefix="lattice_test_runs_")   # never touch the real runs/ folder
