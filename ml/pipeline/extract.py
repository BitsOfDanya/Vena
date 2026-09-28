import os

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline import config

CATEGORY_COLUMNS = ["channel_id", "tag", "system_type", "raw_value"]


def _connect():
    con = duckdb.connect()
    con.execute("PRAGMA threads=6")
    con.execute("SET memory_limit='9GB'")
    con.execute("PRAGMA enable_progress_bar=false")
    return con


def cache_path(sensor_type):
    safe = sensor_type.replace(" ", "_")
    return os.path.join(config.CACHE_DIR, f"events_{safe}.parquet")


def _build_views(con):
    col_types = {
        "ид_события": "VARCHAR", "ид_канала_данных": "VARCHAR", "дата": "VARCHAR",
        "время": "VARCHAR", "тревожное": "VARCHAR", "значение_датчика": "VARCHAR",
    }
    files_sql = "[" + ",".join(f"'{f}'" for f in config.JOURNAL_FILES) + "]"
    types_sql = "{" + ",".join(f"'{k}':'{v}'" for k, v in col_types.items()) + "}"
    con.execute(f"""
        CREATE OR REPLACE VIEW events_all AS
        SELECT ид_события, ид_канала_данных, дата, время, тревожное, значение_датчика
        FROM read_csv({files_sql}, header=True, columns={types_sql}, ignore_errors=False)
        WHERE ид_события != 'ид_события'
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW channels AS
        SELECT * FROM read_csv('{config.CHANNELS_FILE}', header=True, columns={{
            'ид_канала_данных':'VARCHAR','тип_инж_системы':'VARCHAR','тип_датчика':'VARCHAR',
            'тег_инженерной_системы':'VARCHAR','название_датчика':'VARCHAR'
        }})
    """)


def _extract_and_cache(sensor_type, path, batch_rows):
    con = _connect()
    _build_views(con)
    con.execute("""
        SELECT e.ид_канала_данных AS channel_id,
               strptime(e.дата || ' ' || e.время, '%Y-%m-%d %H:%M:%S') AS ts,
               e.тревожное AS alarm_flag,
               e.значение_датчика AS raw_value,
               c.тег_инженерной_системы AS tag,
               c.тип_инж_системы AS system_type
        FROM events_all e
        JOIN channels c ON c.ид_канала_данных = e.ид_канала_данных
        WHERE c.тип_датчика = ?
        ORDER BY e.ид_канала_данных, ts, e.ид_события,
                 e.значение_датчика, e.тревожное
    """, [sensor_type])
    reader = con.to_arrow_reader(batch_rows)

    tmp_path = path + ".tmp"
    writer = None
    n_rows = 0
    try:
        for batch in reader:
            chunk = batch.to_pandas()
            chunk["alarm_flag"] = (chunk["alarm_flag"] == "t").astype("int8")
            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(tmp_path, table.schema, use_dictionary=CATEGORY_COLUMNS)
            writer.write_table(table)
            n_rows += len(chunk)
        if writer is None:
            empty = reader.schema.empty_table()
            empty_df = empty.to_pandas()
            empty_df["alarm_flag"] = empty_df["alarm_flag"].astype("int8")
            table = pa.Table.from_pandas(empty_df, preserve_index=False)
            writer = pq.ParquetWriter(tmp_path, table.schema, use_dictionary=CATEGORY_COLUMNS)
            writer.write_table(table)
    finally:
        if writer is not None:
            writer.close()
    con.close()
    os.replace(tmp_path, path)
    return n_rows


def _read_cached(path):
    table = pq.read_table(path, read_dictionary=CATEGORY_COLUMNS)
    df = table.to_pandas()
    for col in CATEGORY_COLUMNS:
        if df[col].dtype.name != "category":
            df[col] = df[col].astype("category")
    df["alarm_flag"] = df["alarm_flag"].astype("int8")
    return df


def extract_events(sensor_type, force=False, batch_rows=config.EXTRACT_BATCH_ROWS):
    path = cache_path(sensor_type)
    if os.path.exists(path) and not force:
        return _read_cached(path)
    _extract_and_cache(sensor_type, path, batch_rows)
    return _read_cached(path)


def channel_dictionary():
    con = _connect()
    df = con.execute(f"""
        SELECT * FROM read_csv('{config.CHANNELS_FILE}', header=True, columns={{
            'ид_канала_данных':'VARCHAR','тип_инж_системы':'VARCHAR','тип_датчика':'VARCHAR',
            'тег_инженерной_системы':'VARCHAR','название_датчика':'VARCHAR'
        }})
    """).df()
    con.close()
    return df
