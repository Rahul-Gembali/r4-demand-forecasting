#!/usr/bin/env python3
"""Generates the canonical benchmark retail dataset matching Phase 1 & Phase 2 specifications.

Used for rigorous demonstration of raw-to-processed pipeline when external files are pending.
Strictly isolates the 150 target evaluation SKUs and their hidden 8-week sales labels.
"""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Root dir
ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"


def generate_benchmark_datasets() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    np.random.seed(42)

    print("Generating canonical benchmark raw datasets in data/raw/...")

    # 1. Store Clusters
    stores = [
        {"store_id": f"STORE_{i:02d}", "cluster_id": f"CLUSTER_{(i % 3) + 1}", "region": ["North", "South", "East", "West"][i % 4], "store_tier": ["Flagship", "Regional", "Express"][i % 3]}
        for i in range(1, 11)
    ]
    df_stores = pd.DataFrame(stores)
    df_stores.to_csv(RAW_DIR / "store_clusters.csv", index=False)
    print(f"  - Created store_clusters.csv ({len(df_stores)} stores)")

    # 2. Holiday Calendar (2024 to 2026 Monday weeks)
    calendar_rows = []
    start_monday = date(2024, 1, 1)
    holidays = {
        (1, 1): "New Year",
        (3, 29): "Good Friday",
        (7, 4): "Independence Day",
        (10, 31): "Halloween",
        (11, 28): "Thanksgiving / Black Friday",
        (12, 25): "Christmas",
    }
    for w in range(156):  # 3 full years
        curr_monday = start_monday + timedelta(days=w * 7)
        f_year = curr_monday.year
        f_week = curr_monday.isocalendar()[1]

        # Check if week contains any holiday
        h_name = "None"
        is_h = 0
        for day_offset in range(7):
            d = curr_monday + timedelta(days=day_offset)
            if (d.month, d.day) in holidays:
                is_h = 1
                h_name = holidays[(d.month, d.day)]
                break

        calendar_rows.append({
            "week_start_date": curr_monday.strftime("%Y-%m-%d"),
            "fiscal_year": f_year,
            "fiscal_week": f_week,
            "is_holiday_week": is_h,
            "holiday_name": h_name,
        })
    df_calendar = pd.DataFrame(calendar_rows)
    df_calendar.to_csv(RAW_DIR / "holiday_calendar.csv", index=False)
    print(f"  - Created holiday_calendar.csv ({len(df_calendar)} weeks)")

    # 3. Mature SKUs Attributes (~1,200 SKUs)
    categories = {
        "Apparel": ["Jackets", "Hoodies", "T-Shirts", "Jeans", "Trousers"],
        "Footwear": ["Running Shoes", "Sneakers", "Boots", "Sandals"],
        "Accessories": ["Backpacks", "Watches", "Belts", "Caps"],
        "Home": ["Blankets", "Cushions", "Cookware", "Lighting"],
    }
    colours = ["Black", "White", "Navy", "Grey", "Red", "Olive", "Camel", "Blue"]
    materials = ["Cotton", "Polyester", "Wool", "Leather", "Denim", "Linen", "Synthetic"]
    brands = [
        ("Apex Gear", "Tier 1 National"),
        ("Horizon Basics", "Tier 2 Regional"),
        ("ValueCraft", "Tier 3 Value"),
        ("Luxura", "Tier 1 National"),
        ("UrbanThread", "Tier 2 Regional"),
    ]

    mature_skus = []
    historical_sales_rows = []

    for i in range(1, 1201):
        sku_id = f"SKU_HIST_{i:04d}"
        cat = list(categories.keys())[i % len(categories)]
        subcat = categories[cat][i % len(categories[cat])]
        col = colours[i % len(colours)]
        mat = materials[i % len(materials)]
        brand_name, brand_tier = brands[i % len(brands)]
        base_price = round(float(np.random.uniform(18.0, 180.0)), 2)
        has_mkt = bool((i % 3) != 0)  # 66% have marketing support

        # Staggered launch dates across 2024
        launch_week_idx = (i % 40)
        launch_date = (start_monday + timedelta(days=launch_week_idx * 7)).strftime("%Y-%m-%d")

        mature_skus.append({
            "sku_id": sku_id,
            "product_name": f"{brand_name} {cat} {subcat} {col}",
            "category": cat,
            "subcategory": subcat,
            "colour": col,
            "material": mat,
            "base_price": base_price,
            "brand": brand_name,
            "brand_tier": brand_tier,
            "launch_date": launch_date,
            "has_marketing_support": has_mkt,
        })

        # Generate introductory weekly sales for weeks 1 through 8 across store clusters
        # Cold start trajectory: adoption peak at W1-W3, then steady baseline
        for w_age in range(1, 9):
            sale_date = (start_monday + timedelta(days=(launch_week_idx + w_age - 1) * 7)).strftime("%Y-%m-%d")
            # Select 3 to 6 stores stocking the product
            store_sample = np.random.choice(df_stores["store_id"], size=np.random.randint(3, 7), replace=False)
            for store_id in store_sample:
                # Base volume influenced by price, marketing, brand tier, and launch age
                mkt_boost = 1.35 if (has_mkt and w_age <= 4) else 1.0
                tier_mult = 1.25 if brand_tier == "Tier 1 National" else (1.0 if brand_tier == "Tier 2 Regional" else 0.8)
                decay = np.exp(-0.08 * (w_age - 1))
                price_elasticity = (100.0 / base_price) ** 0.4
                mu = 25.0 * mkt_boost * tier_mult * decay * price_elasticity

                # Realistic Poisson/NegBin sales count with genuine zeros
                units = float(np.random.poisson(max(0.5, mu)))
                # Occasional genuine zero sales
                if np.random.rand() < 0.08:
                    units = 0.0

                historical_sales_rows.append({
                    "sku_id": sku_id,
                    "store_id": store_id,
                    "week_start_date": sale_date,
                    "units_sold": units,
                    "revenue": round(units * base_price, 2),
                })

    df_mature = pd.DataFrame(mature_skus)
    df_mature.to_csv(RAW_DIR / "mature_sku_attributes.csv", index=False)
    print(f"  - Created mature_sku_attributes.csv ({len(df_mature)} SKUs)")

    df_sales = pd.DataFrame(historical_sales_rows)
    df_sales.to_csv(RAW_DIR / "historical_sales.csv", index=False)
    print(f"  - Created historical_sales.csv ({len(df_sales)} sales transactions)")

    # 4. Target Evaluation SKUs Attributes (Exactly 150 SKUs with zero sales history)
    eval_skus = []
    hidden_labels = []
    eval_launch_monday = date(2025, 11, 3)

    for i in range(1, 151):
        sku_id = f"SKU_EVAL_{i:03d}"
        cat = list(categories.keys())[i % len(categories)]
        subcat = categories[cat][i % len(categories[cat])]
        col = colours[(i + 2) % len(colours)]
        mat = materials[(i + 3) % len(materials)]
        brand_name, brand_tier = brands[(i + 1) % len(brands)]
        base_price = round(float(np.random.uniform(22.0, 195.0)), 2)
        has_mkt = bool((i % 2) == 0)

        eval_skus.append({
            "sku_id": sku_id,
            "product_name": f"{brand_name} New {subcat} {col}",
            "category": cat,
            "subcategory": subcat,
            "colour": col,
            "material": mat,
            "base_price": base_price,
            "brand": brand_name,
            "brand_tier": brand_tier,
            "launch_date": eval_launch_monday.strftime("%Y-%m-%d"),
            "has_marketing_support": has_mkt,
        })

        # Hidden ground-truth labels for evaluation (W1 through W8)
        # Kept isolated in hidden_evaluation_labels.csv
        for w_age in range(1, 9):
            mkt_boost = 1.35 if (has_mkt and w_age <= 4) else 1.0
            tier_mult = 1.25 if brand_tier == "Tier 1 National" else (1.0 if brand_tier == "Tier 2 Regional" else 0.8)
            decay = np.exp(-0.08 * (w_age - 1))
            price_elasticity = (100.0 / base_price) ** 0.4
            # Aggregate enterprise weekly sales
            true_sales = float(np.random.poisson(max(5.0, 95.0 * mkt_boost * tier_mult * decay * price_elasticity)))

            hidden_labels.append({
                "sku_id": sku_id,
                "horizon_week": w_age,
                "actual_sales": true_sales,
            })

    df_eval = pd.DataFrame(eval_skus)
    df_eval.to_csv(RAW_DIR / "new_sku_attributes.csv", index=False)
    print(f"  - Created new_sku_attributes.csv ({len(df_eval)} cold-start target SKUs)")

    df_hidden = pd.DataFrame(hidden_labels)
    df_hidden.to_csv(RAW_DIR / "hidden_evaluation_labels.csv", index=False)
    print(f"  - Created hidden_evaluation_labels.csv ({len(df_hidden)} rows - ISOLATED LABELS)")

    print("\nBenchmark generation completed successfully.")


if __name__ == "__main__":
    generate_benchmark_datasets()
