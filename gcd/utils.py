from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from loguru import logger


class GitHandler:
    """
    Handles git operations including cloning, caching, and repository management.
    """

    def __init__(
        self,
        github_token: str | None = None,
        cache_dir: str | None = None,
        clone_timeout: int = 300,
        debug: bool = False,
    ):
        self.github_token = github_token
        self.cache_dir = cache_dir
        self.clone_timeout = clone_timeout
        self.debug = debug
        self._clone_cache = {}

        # Initialize cache from existing directories if cache_dir is provided
        if self.cache_dir:
            self._initialize_cache_from_directory()

    def _initialize_cache_from_directory(self):
        """
        Initialize the clone cache by scanning the cache directory for existing repositories.
        """
        if not self.cache_dir:
            return

        cache_path = Path(self.cache_dir)

        # Check if cache directory exists
        if not cache_path.exists():
            logger.info(
                f"Cache directory {cache_path} does not exist, will be created when needed",
            )
            return

        if not cache_path.is_dir():
            logger.warning(f"Cache path {cache_path} exists but is not a directory")
            return

        logger.info(f"Scanning cache directory: {cache_path}")

        try:
            # Look for directories that match the pattern "owner_repo"
            for item in cache_path.iterdir():
                if not item.is_dir():
                    continue

                # Check if it's a valid git repository (has .git folder)
                if not (item / ".git").exists():
                    logger.debug(f"Skipping {item.name} - not a git repository")
                    continue

                # Parse directory name to extract owner/repo
                dir_name = item.name

                # Expected format: "owner_repo"
                # Split on underscore, but be careful as repo names can contain underscores
                # We'll assume the first underscore separates owner from repo
                if "_" not in dir_name:
                    logger.debug(
                        f"Skipping {dir_name} - doesn't match expected pattern 'owner_repo'",
                    )
                    continue

                # Split only on the first underscore
                parts = dir_name.split("_", 1)
                if len(parts) != 2:
                    logger.debug(f"Skipping {dir_name} - invalid format")
                    continue

                owner, repo = parts
                repo_key = f"{owner}/{repo}"

                # Add to cache
                self._clone_cache[repo_key] = str(item)
                logger.info(f"Added {repo_key} to cache: {item}")

        except Exception as e:
            logger.error(f"Error scanning cache directory: {e}")
            return

        logger.info(f"Initialized cache with {len(self._clone_cache)} repositories")
        if self.debug:
            logger.debug(f"Cache contents: {self._clone_cache}")

    def is_valid_git_repo(self, path: str | Path) -> bool:
        """Check if a directory is a valid git repository."""
        path = Path(path)
        return path.exists() and path.is_dir() and (path / ".git").exists()

    def get_clone_url(self, owner: str, repo: str, use_https: bool = True) -> str:
        """Get the appropriate clone URL."""
        if use_https:
            if self.github_token:
                return f"https://{self.github_token}@github.com/{owner}/{repo}.git"
            else:
                return f"https://github.com/{owner}/{repo}.git"
        else:
            return f"git@github.com:{owner}/{repo}.git"

    def clone_repository(
        self,
        owner: str,
        repo: str,
        target_dir: str,
        shallow: bool = True,
    ) -> bool:
        """Clone repository to target directory with timeout."""
        clone_url = self.get_clone_url(owner, repo)

        # Build git clone command
        cmd = ["git", "clone"]
        if shallow:
            cmd.extend(["--depth", "1"])  # Shallow clone for speed
        cmd.extend([clone_url, target_dir])

        logger.info(f"Cloning {owner}/{repo} to {target_dir}")

        try:
            # Use subprocess with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.clone_timeout,
            )

            if result.returncode == 0:
                logger.info(f"Successfully cloned {owner}/{repo}")
                return True
            else:
                logger.error(f"Git clone failed: {result.stderr}")
                # Try without token (for public repos)
                if (
                    self.github_token
                    and "authentication failed" in result.stderr.lower()
                ):
                    logger.info("Retrying without token for public repo")
                    public_url = f"https://github.com/{owner}/{repo}.git"
                    cmd[-2] = public_url
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=self.clone_timeout,
                    )
                    if result.returncode == 0:
                        logger.info(f"Successfully cloned {owner}/{repo} (public)")
                        return True
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Clone timeout after {self.clone_timeout} seconds")
            return False
        except FileNotFoundError:
            logger.error("Git not found. Please install git.")
            return False
        except Exception as e:
            logger.error(f"Clone error: {e}")
            return False

    def update_repository(self, repo_path: str | Path) -> bool:
        """Update an existing git repository (git pull)."""
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=self.clone_timeout,
            )

            if result.returncode == 0:
                logger.info(f"Successfully updated repository at {repo_path}")
                return True
            else:
                logger.warning(f"Git pull failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Update timeout after {self.clone_timeout} seconds")
            return False
        except Exception as e:
            logger.error(f"Update error: {e}")
            return False

    @contextmanager
    def _get_clone_directory(self, owner: str, repo: str):
        """Context manager for getting a clone directory - uses cache_dir if available, temp otherwise."""
        if self.cache_dir:
            # Use cache directory - persistent storage
            cache_path = Path(self.cache_dir)
            # Create the cache directory if it doesn't exist
            cache_path.mkdir(parents=True, exist_ok=True)

            try:
                yield str(cache_path)
            except Exception:
                # Don't cleanup cache directory on error - might be useful for debugging
                raise
        else:
            # Use temporary directory - auto cleanup
            with tempfile.TemporaryDirectory(
                prefix=f"github_search_{owner}_{repo}_",
                delete=True,
            ) as temp_dir:
                yield temp_dir

    def get_repository_path(
        self,
        owner: str,
        repo: str,
        update_existing: bool = False,
    ) -> str | None:
        """
        Get the local path to a repository, cloning it if necessary.

        Args:
            owner: Repository owner
            repo: Repository name
            update_existing: Whether to update existing repositories

        Returns:
            Path to the local repository, or None if failed
        """
        repo_key = f"{owner}/{repo}"

        if self.debug:
            logger.debug(f"Clone cache: {self._clone_cache}")

        # Check if we already have this repo cloned in cache
        if repo_key in self._clone_cache:
            clone_dir = self._clone_cache[repo_key]
            if self.is_valid_git_repo(clone_dir):
                if update_existing:
                    logger.info(f"Updating existing repository at {clone_dir}")
                    self.update_repository(clone_dir)
                else:
                    logger.info(f"Using cached clone at {clone_dir}")

                return clone_dir
            else:
                # Remove stale cache entry
                del self._clone_cache[repo_key]

        # Use context manager for directory handling
        with self._get_clone_directory(owner, repo) as clone_base:
            # Create the full path where we want the repo to be cloned
            clone_path = Path(clone_base) / f"{owner}_{repo}"

            logger.debug(f"Target clone path: {clone_path}")

            # Check if repository is already cloned at this location
            if self.is_valid_git_repo(clone_path):
                logger.info(f"Repository already exists at {clone_path}")
                if update_existing:
                    logger.info("Updating existing repository")
                    self.update_repository(clone_path)
                # Update cache with existing clone
                self._clone_cache[repo_key] = str(clone_path)
                return str(clone_path)
            else:
                # Remove directory if it exists but is not a valid git repo
                if clone_path.exists():
                    logger.info(
                        f"Removing invalid/incomplete directory at {clone_path}",
                    )
                    try:
                        shutil.rmtree(clone_path)
                    except Exception as e:
                        logger.error(f"Failed to remove existing directory: {e}")
                        return None

                # Ensure parent directory exists
                clone_path.parent.mkdir(parents=True, exist_ok=True)

                logger.debug(f"Cloning to: {clone_path}")

                # Clone repository directly to the target path
                if not self.clone_repository(owner, repo, str(clone_path)):
                    logger.error("Failed to clone repository!")
                    return None

                # Cache the clone path for this session
                self._clone_cache[repo_key] = str(clone_path)
                return str(clone_path)

    def get_cache_info(self) -> dict:
        """Get information about the current cache."""
        return {
            "cache_dir": self.cache_dir,
            "cached_repos": list(self._clone_cache.keys()),
            "cache_size": len(self._clone_cache),
        }

    def cleanup_cache(self):
        """Cleanup cloned repositories."""
        for repo_key, clone_path in self._clone_cache.items():
            try:
                if os.path.exists(clone_path):
                    shutil.rmtree(clone_path)
                    logger.info(f"Cleaned up {repo_key} cache")
            except Exception as e:
                logger.error(f"Error cleaning up {repo_key}: {e}")
        self._clone_cache.clear()

    def __del__(self):
        """Cleanup on destruction."""
        if not self.cache_dir:  # Only cleanup if using temp directories
            self.cleanup_cache()
