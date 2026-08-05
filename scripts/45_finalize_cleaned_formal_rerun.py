from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "finalize_cleaned_rerun_main",
            module_name="prta_cxr.cleaned_rerun",
        )
    )

