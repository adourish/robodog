"""Show all Todoist tasks"""
import requests, json

r = requests.post('http://localhost:2500', 
    headers={'Authorization': 'Bearer testtoken', 'Content-Type': 'text/plain'},
    data='TODOIST_TASKS {}')

tasks = r.json()['tasks']
print(f'\n=== TODOIST TASKS ({len(tasks)} total) ===\n')

for i, t in enumerate(tasks, 1):
    status = "✅" if t.get("is_completed") else "⬜"
    priority = t.get("priority", 1)
    priority_str = "🔴" if priority == 4 else "🟡" if priority == 3 else "🔵" if priority == 2 else "⚪"
    print(f'{i}. {status} {priority_str} {t["content"]}')
