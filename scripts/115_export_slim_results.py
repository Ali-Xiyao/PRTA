from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("export_slim_results_main", module_name="prta_cxr.slim_export")
    )
