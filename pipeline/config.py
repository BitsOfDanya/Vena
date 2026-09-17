import os

ROOT = os.environ.get("LCT_PROJECT_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATASET_DIR = os.path.join(ROOT, "dataset")
ANALYSIS_DIR = os.path.join(ROOT, "analysis")
CACHE_DIR = os.path.join(ANALYSIS_DIR, "ml_ready", "cache")
TABLES_DIR = os.path.join(ANALYSIS_DIR, "tables")
PLOTS_DIR = os.path.join(ANALYSIS_DIR, "plots")

os.makedirs(CACHE_DIR, exist_ok=True)

YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
JOURNAL_FILES = [os.path.join(DATASET_DIR, f"ext-journal-{y}.csv") for y in YEARS]
CHANNELS_FILE = os.path.join(DATASET_DIR, "справочник_каналов_датчиков.csv")

TRAIN_YEARS = (2019, 2023)
VALID_YEAR = 2024
TEST_YEARS = (2025, 2026)

FAULT_LITERAL = "Неисправен"
FAULT_ADJACENT_LITERALS = [
    "Обесточен",
    "Батарея неисправна",
    "Батарея разряжена",
    "Много неисправных устройств",
]

NUMERIC_DOMINANT_SENSOR_TYPES = {"Газовый датчик", "Датчик температуры"}

DEVICE_TYPES = [
    "Датчик дыма",
    "Состояние насоса",
    "Состояние вентилятора",
    "Газовый датчик",
    "Датчик температуры",
    "Состояние фазы",
]

PRIMARY_DEVICE_TYPES = ["Состояние насоса", "Состояние вентилятора"]
SECONDARY_DEVICE_TYPES = ["Датчик дыма"]

SENSOR_ALIASES = {
    "smoke": "Датчик дыма",
    "pump": "Состояние насоса",
    "fan": "Состояние вентилятора",
    "gas": "Газовый датчик",
    "temperature": "Датчик температуры",
    "phase": "Состояние фазы",
}

EPISODE_GAP_HOURS = 6
SILENCE_CHECKPOINT_HOURS = 24
SILENCE_MAX_CHECKPOINTS = 14
BURST_INTERARRIVAL_PERCENTILE = 5
BURST_MIN_HISTORY_EVENTS = 20

HORIZONS_HOURS = [24, 48, 72]
DEFAULT_HORIZON_HOURS = 24

TAG_GROUP_LEVELS = 3

CHRONIC_FAILURE_LOOKBACK_DAYS = 90
CHRONIC_MIN_HISTORICAL_FAILURES = 2
CHRONIC_QUANTILE_OPTIONS = [0.5, 0.67, 0.75]

EXTRACT_BATCH_ROWS = 2_000_000

RANDOM_SEED = 42

DUTY_CYCLE_SENSOR_TYPES = {"Состояние насоса", "Состояние вентилятора"}

PRIOR_SMOOTHING_ALPHA = 10.0

ROLLING_FOLDS = [
    {"name": "fold1", "train_end": 2021, "valid_year": 2022},
    {"name": "fold2", "train_end": 2022, "valid_year": 2023},
    {"name": "fold3", "train_end": 2023, "valid_year": 2024},
    {"name": "fold4", "train_end": 2024, "valid_year": 2025},
]
STABILITY_CHECK_FOLD = {"name": "stability_2026h1", "train_end": 2025,
                         "valid_start": "2026-01-01", "valid_end": "2026-06-30"}

ALERT_COOLDOWN_HOURS_OPTIONS = [24, 48, 72]
DAILY_TOPK_FRACTIONS = [0.001, 0.005, 0.01, 0.02, 0.05]
DAILY_TOPK_FIXED_COUNTS = [5, 10, 20, 50]

RISK_LEVEL_TARGET_PRECISIONS = {"critical": 0.5, "high": 0.3, "medium": 0.1}
