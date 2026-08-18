from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "watch_phase20_continuation_main",
            module_name="prta_cxr.phase20_continuation_watcher",
        )
    )
