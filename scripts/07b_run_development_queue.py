from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("run_development_queue_main", module_name="prta_cxr.cli_queue")
    )
