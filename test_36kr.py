
import sys
sys.path.insert(0, "/mnt/c/Users/Admin/Desktop/investment-radar/src")
from 采集.news_36kr import News36krCollector

config = {"source_id": "36kr_tech", "name": "36kr 科技新闻", "enabled": True}
collector = News36krCollector(config)
result = collector.run()

print(f"success: {result.success}")
print(f"count: {result.total_count}")
if result.data:
    for i, item in enumerate(result.data[:3]):
        print(f"  [{i+1}] {item['title']}")
        print(f"      URL: {item['url']}")
        print(f"      desc: {item['description'][:80]}...")
        print(f"      date: {item['published_at']}")
        print()
if result.error:
    print(f"ERROR: {result.error}")
