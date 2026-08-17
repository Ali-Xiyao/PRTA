from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "source_held_out_evaluation_main",
            module_name="prta_cxr.source_held_out_evaluation",
        )
    )
