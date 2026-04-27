import argparse
import logging
import socket
import sys

import osc.conf
import urllib3.exceptions

from .cmd_build import cmd_build_dependency, cmd_build_status, cmd_build_trigger
from .cmd_profile import (
    _load_profile,
    _load_profile_env_strings,
    cmd_profile_create,
    cmd_profile_list,
)
from .cmd_project import (
    cmd_project_config,
    cmd_project_install,
    cmd_project_release,
    cmd_project_verify,
    cmd_project_versions,
)
from .cmd_sync import (
    cmd_sync,
    cmd_sync_delete,
    cmd_sync_promote,
    cmd_sync_release,
)
from .common import _DIM, _col, logger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="percona-obs",
        description="Manage Percona packages on an OBS instance.",
    )
    parser.add_argument(
        "-A",
        "--apiurl",
        metavar="URL",
        help="OBS API URL (e.g. http://my-obs-instance.local:8000)",
    )
    parser.add_argument(
        "-R",
        "--rootprj",
        metavar="PROJECT",
        help="OBS root project under which all projects are deployed (e.g. home:username)",
    )
    parser.add_argument(
        "-P",
        "--profile",
        metavar="NAME",
        help="Load OBS connection settings from .profile/<NAME>.yaml "
        "(sets apiurl and rootprj; explicit -A/-R override the profile values).",
    )
    parser.add_argument(
        "-e",
        "--env",
        metavar="KEY:VALUE",
        action="append",
        default=[],
        dest="env_overrides",
        help="Define an env variable as KEY:VALUE (VALUE may be empty, e.g. KEY:). "
        "Can be repeated. Supplements or overrides the active profile's env section.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print debug-level log messages (API calls, unchanged items) to stdout.",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    subparsers.required = True

    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync local packaging files to OBS, or delete synced projects/packages.",
    )
    sync_subparsers = sync_parser.add_subparsers(
        dest="sync_command", metavar="<subcommand>"
    )
    sync_subparsers.required = True

    sync_push_parser = sync_subparsers.add_parser(
        "push",
        help="Sync local packaging files to OBS, creating or updating projects and packages.",
    )
    sync_push_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Project name (colon notation, e.g. ppg:17.9) or top-level package name. "
        "If omitted, all packages and projects under root/ are synced.",
    )
    sync_push_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        help="Package name to sync. If omitted, all packages and subprojects under the project are synced.",
    )
    sync_push_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force update even if OBS reports a conflict.",
    )
    sync_push_parser.add_argument(
        "-m",
        "--message",
        default="",
        metavar="MSG",
        help="Commit message recorded in the OBS source revision when files are uploaded.",
    )
    sync_push_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run local services but skip all OBS write calls. "
        "Use to verify service output and the upload diff without committing to OBS.",
    )
    sync_push_parser.add_argument(
        "--no-services",
        action="store_true",
        default=False,
        help="Skip running local OBS services (mode=manual). Upload obs/ files as-is.",
    )
    sync_push_parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable the service artifact cache; always run manual services (e.g. go_modules).",
    )
    sync_push_parser.add_argument(
        "--non-recursive",
        action="store_true",
        default=False,
        dest="non_recursive",
        help="Only sync packages directly under the specified project; do not descend into subprojects.",
    )
    sync_push_parser.add_argument(
        "--project-only",
        action="store_true",
        default=False,
        dest="project_only",
        help="Only sync project configuration (meta and build config); skip all package syncing.",
    )
    sync_push_parser.add_argument(
        "--no-scm-validate",
        action="store_true",
        default=False,
        dest="no_scm_validate",
        help="Skip validation of obs_scm git revisions before syncing.",
    )
    sync_push_parser.add_argument(
        "--branch-from",
        metavar="PROFILE",
        default=None,
        dest="branch_from",
        help="For packages unchanged since the given profile's last sync, create an "
        "_aggregate that reuses pre-built binaries from that profile's OBS project "
        "instead of uploading sources. Both profiles must share the same OBS instance.",
    )
    sync_push_parser.set_defaults(func=cmd_sync)

    sync_delete_parser = sync_subparsers.add_parser(
        "delete",
        help="Delete OBS projects (and sub-projects) or a single package.",
    )
    sync_delete_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Project name (colon notation, e.g. ppg:17.9). "
        "If omitted, the full project tree under rootprj is deleted.",
    )
    sync_delete_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        help="Package name. If provided, only this package is deleted (project is required).",
    )
    sync_delete_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="Skip the confirmation prompt.",
    )
    sync_delete_parser.add_argument(
        "--recursive",
        action="store_true",
        default=False,
        help="Delete projects even if they still contain packages.",
    )
    sync_delete_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be deleted without making any changes.",
    )
    sync_delete_parser.set_defaults(func=cmd_sync_delete)

    sync_promote_parser = sync_subparsers.add_parser(
        "promote",
        help="Replace _aggregate (branch) packages with their full local source files.",
    )
    sync_promote_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Project name (colon notation, e.g. ppg:17.9) or top-level package name. "
        "If omitted, all packages under root/ are targeted.",
    )
    sync_promote_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        help="Package name. If omitted, all packages under the project are targeted.",
    )
    sync_promote_parser.add_argument(
        "-m",
        "--message",
        default="",
        metavar="MSG",
        help="Commit message recorded in the OBS source revision when files are uploaded.",
    )
    sync_promote_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be promoted without writing anything to OBS.",
    )
    sync_promote_parser.add_argument(
        "--no-services",
        action="store_true",
        default=False,
        help="Skip running local OBS services (mode=manual). Upload obs/ files as-is.",
    )
    sync_promote_parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable the service artifact cache; always run manual services (e.g. go_modules).",
    )
    sync_promote_parser.set_defaults(func=cmd_sync_promote)

    sync_release_parser = sync_subparsers.add_parser(
        "release",
        help="Release packages from OBS source project to release target.",
    )
    sync_release_parser.add_argument(
        "project",
        help="Release project identifier (e.g. ppg:releases:17.9).",
    )
    sync_release_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Skip source project sync validation.",
    )
    sync_release_parser.add_argument(
        "--skip-tag-check",
        action="store_true",
        default=False,
        help="Skip the git tag divergence check (Check 1). "
        "Use when the release tag has not been created locally yet.",
    )
    sync_release_parser.set_defaults(func=cmd_sync_release)

    build_parser_ = subparsers.add_parser(
        "build",
        help="Trigger OBS builds or check their status.",
    )
    build_subparsers = build_parser_.add_subparsers(
        dest="build_command", metavar="<subcommand>"
    )
    build_subparsers.required = True

    _build_project_help = (
        "Project name (colon notation, e.g. ppg:17.9) or top-level package name. "
        "If omitted, all packages under root/ are targeted."
    )
    _build_package_help = (
        "Package name. If omitted, all packages under the project are targeted."
    )

    build_trigger_parser = build_subparsers.add_parser(
        "trigger",
        help="Trigger an OBS service run for one or more packages.",
    )
    build_trigger_parser.add_argument(
        "project", nargs="?", default=None, help=_build_project_help
    )
    build_trigger_parser.add_argument(
        "package", nargs="?", default=None, help=_build_package_help
    )
    build_trigger_parser.set_defaults(func=cmd_build_trigger)

    build_status_parser = build_subparsers.add_parser(
        "status",
        help="Show build status of packages as a tree.",
    )
    build_status_parser.add_argument(
        "project", nargs="?", default=None, help=_build_project_help
    )
    build_status_parser.add_argument(
        "package", nargs="?", default=None, help=_build_package_help
    )
    build_status_parser.add_argument(
        "--repo",
        metavar="NAME",
        default=None,
        help="Filter output to a specific repository name (e.g. RockyLinux_9).",
    )
    build_status_parser.set_defaults(func=cmd_build_status)

    build_dep_parser = build_subparsers.add_parser(
        "dependency",
        help="Show local build dependency trees derived from OBS build results.",
    )
    build_dep_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Restrict to packages under this project (colon notation, e.g. ppg:17.9). "
        "If omitted, all packages under root/ are included.",
    )
    build_dep_parser.set_defaults(func=cmd_build_dependency)

    profile_parser = subparsers.add_parser(
        "profile",
        help="Manage connection profiles.",
    )
    profile_subparsers = profile_parser.add_subparsers(
        dest="profile_command", metavar="<subcommand>"
    )
    profile_subparsers.required = True

    profile_create_parser = profile_subparsers.add_parser(
        "create",
        help="Create or update a connection profile from -A and -R values.",
    )
    profile_create_parser.add_argument(
        "name",
        help="Profile name (saved as .profile/<name>.yaml).",
    )
    profile_create_parser.set_defaults(func=cmd_profile_create)

    profile_list_parser = profile_subparsers.add_parser(
        "list",
        help="List available connection profiles and their settings.",
    )
    profile_list_parser.set_defaults(func=cmd_profile_list)

    project_parser = subparsers.add_parser(
        "project",
        help="Manage local project configuration.",
    )
    project_subparsers = project_parser.add_subparsers(
        dest="project_command", metavar="<subcommand>"
    )
    project_subparsers.required = True

    project_verify_parser = project_subparsers.add_parser(
        "verify",
        help="Validate local project configuration (subproject: references, env variable usage).",
    )
    project_verify_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Restrict validation to this subproject (colon notation, e.g. ppg:17.9). "
        "If omitted, the entire root/ tree is validated.",
    )
    project_verify_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        help="Restrict validation to this package within the project. Requires project.",
    )
    project_verify_parser.set_defaults(func=cmd_project_verify)

    project_install_parser = project_subparsers.add_parser(
        "install",
        help="Show repository installation instructions for testing built packages.",
    )
    project_install_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Restrict output to this subproject (colon notation, e.g. ppg:17.9). "
        "If omitted, all installable projects under root/ are included.",
    )
    project_install_parser.add_argument(
        "--repo",
        metavar="NAME",
        default=None,
        help="Filter output to a specific repository name (e.g. Debian_13).",
    )
    project_install_parser.set_defaults(func=cmd_project_install)

    project_config_parser = project_subparsers.add_parser(
        "config",
        help="Show the project meta XML and build config that would be sent to OBS.",
    )
    project_config_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Restrict output to this subproject and its children (colon notation, e.g. ppg:17.9). "
        "If omitted, all projects under root/ are shown.",
    )
    project_config_parser.add_argument(
        "--offline",
        action="store_true",
        default=False,
        help="Do not connect to OBS. Show only the locally-generated meta "
        "without merging OBS-managed elements (person/group/lock/link).",
    )
    project_config_parser.set_defaults(func=cmd_project_config)

    project_versions_parser = project_subparsers.add_parser(
        "versions",
        help="List all packages with their upstream version (YAML to stdout).",
    )
    project_versions_parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Restrict to this project (colon notation, e.g. ppg:17). "
        "If omitted, all packages under root/ are listed.",
    )
    project_versions_parser.add_argument(
        "package",
        nargs="?",
        default=None,
        help="Show only this package. Requires project.",
    )
    project_versions_parser.add_argument(
        "--recursive",
        action="store_true",
        default=False,
        help="Also list packages in subprojects.",
    )
    project_versions_parser.add_argument(
        "--online",
        action="store_true",
        default=False,
        help="Query the OBS instance for the last successfully built version "
        "(includes release number, e.g. 3.5.26-6.1). Requires -P/--profile or "
        "-A/-R. For packages: replaces version. For container images: adds a "
        "version field alongside image and tag.",
    )
    project_versions_parser.add_argument(
        "--markdown",
        action="store_true",
        default=False,
        help="Output a Markdown table instead of YAML.",
    )
    project_versions_parser.set_defaults(func=cmd_project_versions)

    project_release_parser = project_subparsers.add_parser(
        "release",
        help="Cut a release: create release.yaml, commit, and tag.",
    )
    project_release_parser.add_argument(
        "project",
        help="Source project to release from (colon notation, e.g. ppg:17).",
    )
    project_release_parser.add_argument(
        "release_name",
        metavar="release-name",
        help="Release name (e.g. 17.9). Used as the subdirectory under releases/.",
    )
    project_release_parser.set_defaults(func=cmd_project_release)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Resolve profile values; explicit -A / -R / -e always take precedence.
    if args.profile:
        profile = _load_profile(args.profile)
        if not args.apiurl:
            args.apiurl = profile.get("apiurl")
        if not args.rootprj:
            args.rootprj = profile.get("rootprj")
        # Prepend profile env so CLI -e flags (appended later) override them.
        args.env_overrides = (
            _load_profile_env_strings(args.profile) + args.env_overrides
        )

    _local_only_commands = ("profile", "project")

    if args.command not in _local_only_commands and not args.rootprj:
        parser.error(
            "rootprj is required: supply -R/--rootprj or use -P/--profile <name>"
        )

    if args.verbose:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(f"  {_col(_DIM, '·')} %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

    if args.command not in _local_only_commands:
        osc.conf.get_config(override_apiurl=args.apiurl)
        socket.setdefaulttimeout(30)

    try:
        args.func(args)
    except urllib3.exceptions.MaxRetryError as e:
        host = f"{e.pool.host}:{e.pool.port}" if e.pool else args.apiurl or "OBS"
        print(f"error: cannot connect to OBS ({host}): {e.reason}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        import errno

        if e.errno in (errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ETIMEDOUT):
            print(
                f"error: cannot connect to OBS ({args.apiurl or 'unknown'}): {e.strerror}",
                file=sys.stderr,
            )
            sys.exit(1)
        raise
