# Empty on purpose: its presence makes pytest add the repository root to
# sys.path (pytest's "rootdir insertion" for import mode "prepend"), so
# `tests/test_provider_resolution.py` can `import percona_obs` without the
# package being installed.
