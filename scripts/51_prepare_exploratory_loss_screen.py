from _bootstrap import dispatch

if __name__ == "__main__":
    raise SystemExit(
        dispatch(
            "prepare_loss_screen_main",
            module_name="prta_cxr.exploratory_tuning",
        )
    )
