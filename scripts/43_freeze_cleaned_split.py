from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "freeze_cleaned_split_main",
            module_name="prta_cxr.cleaned_split_freeze",
        )
    )
