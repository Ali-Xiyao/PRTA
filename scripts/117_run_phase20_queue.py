from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "run_phase20_queue_main",
            module_name="prta_cxr.phase20_queue_runner",
        )
    )
