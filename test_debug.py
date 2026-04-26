
import sys
sys.path.insert(0, "/mnt/c/Users/Admin/Desktop/investment-radar")
from src.core.config import get_config
from src.core.database import init_db
init_db()
config = get_config()

# Test get_detection_rules
rules = config.get_detection_rules("ai_llm")
print(f"rules type: {type(rules)}, len: {len(rules)}")
for r in rules:
    print(f"  rule type: {type(r)}, keys: {r.keys() if hasattr(r, 'keys') else 'N/A'}")

# Test paper detector
from src.检测.paper_detector import PaperBurstDetector
from src.采集.arxiv import ArxivCollector
source = config.get_source_config("ai_llm", "arxiv_cs_ai")
col = ArxivCollector(source)
result = col.run()
print(f"arxiv data type: {type(result.data)}, len: {len(result.data)}")
if result.data:
    print(f"  first item type: {type(result.data[0])}")

detector = PaperBurstDetector(thresholds={"high": 20, "medium": 10})
try:
    alerts = detector.detect(result.data)
    print(f"paper alerts: {len(alerts)}")
except Exception as e:
    print(f"paper detector ERROR: {e}")
    import traceback; traceback.print_exc()
