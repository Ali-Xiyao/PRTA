from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch("run_phase16_queue_main", module_name="prta_cxr.phase16_queue_runner")
    )
