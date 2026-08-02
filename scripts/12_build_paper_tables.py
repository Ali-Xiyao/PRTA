from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("paper_tables_main", module_name="prta_cxr.cli_tables")
    )
