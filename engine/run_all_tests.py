"""Run every test. The agent runs this before its first order each session."""
import os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
loader = unittest.TestLoader()
suite = unittest.TestSuite([
    loader.discover(HERE, pattern="test_risk_engine.py"),
    loader.discover(HERE, pattern="test_doc_consistency.py"),
])
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful():
    print("\n*** RISK MATH OR DOCUMENT CONSISTENCY FAILED — DO NOT TRADE ***")
sys.exit(0 if result.wasSuccessful() else 1)
