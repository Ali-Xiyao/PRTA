from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "run_ifusion_queue_main",
            module_name="prta_cxr.ifusion_queue",
        )
    )
