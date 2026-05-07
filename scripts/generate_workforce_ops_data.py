import random
from datetime import datetime, timedelta

import pandas as pd


random.seed(42)

regions = ["West", "Central", "East"]
sites = ["SEA1", "SEA2", "PHX1", "DAL1", "ATL1"]
teams = ["Inbound", "Outbound", "Support"]
managers = ["Manager A", "Manager B", "Manager C", "Manager D"]
shifts = ["Morning", "Afternoon", "Night"]
tenure_bands = ["0-3 months", "3-12 months", "1-3 years", "3+ years"]
cohorts = ["New Hire", "Experienced"]

start_date = datetime(2026, 1, 1)
rows = []

for i in range(5000):
    record_date = start_date + timedelta(days=random.randint(0, 179))

    scheduled_start = record_date.replace(
        hour=random.choice([6, 8, 14, 22]),
        minute=0,
        second=0,
        microsecond=0,
    )

    site = random.choice(sites)
    shift = random.choice(shifts)
    team = random.choice(teams)
    manager = random.choice(managers)

    is_late = random.random() < 0.18
    adherence_minutes = random.randint(1, 35) if is_late else random.randint(-8, 3)
    actual_start = scheduled_start + timedelta(minutes=adherence_minutes)

    total_tasks = random.randint(40, 120)
    completed_tasks = max(
        0,
        min(total_tasks, int(total_tasks * random.uniform(0.75, 1.0)))
    )

    utilization_rate = round(random.uniform(0.55, 0.95), 3)

    rows.append(
        {
            "record_date": record_date.date().isoformat(),
            "region": random.choice(regions),
            "site": site,
            "team": team,
            "manager_name": manager,
            "shift": shift,
            "employee_id": f"E{random.randint(1000, 9999)}",
            "scheduled_start_ts": scheduled_start.isoformat(),
            "actual_start_ts": actual_start.isoformat(),
            "is_late": int(is_late),
            "adherence_minutes": adherence_minutes,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "utilization_rate": utilization_rate,
            "tenure_band": random.choice(tenure_bands),
            "cohort": random.choice(cohorts),
        }
    )

df = pd.DataFrame(rows)

output_path = "domains/workforce_ops/sample.csv"
df.to_csv(output_path, index=False)

print(f"Saved {output_path}")
print(df.shape)
print(df.head())