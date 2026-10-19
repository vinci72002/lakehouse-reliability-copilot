"""Local Spark session used to check Databricks-shaped transforms.

Databricks supplies its own session. This builder is only for Phase 1
tests on a workstation. Table files are written by delta_store, so the
local session does not need Hadoop native binaries.
"""

import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession


def build_local_spark(warehouse_dir: Path) -> SparkSession:
    warehouse_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    spark = (
        SparkSession.builder.appName("lakehouse-reliability-copilot")
        .master("local[1]")
        .config("spark.ui.enabled", "false")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.driver.memory", "1g")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.local.dir", str(warehouse_dir / "tmp"))
        .config("spark.sql.warehouse.dir", str(warehouse_dir / "warehouse"))
        .config("spark.sql.catalogImplementation", "in-memory")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark
