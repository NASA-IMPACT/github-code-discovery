from __future__ import annotations

from abc import ABC, abstractmethod
import ast
import json
import os
import time
import ast
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
import subprocess
import threading
from typing import Optional
from urllib.parse import urlparse

import requests
from loguru import logger

from gcd.schema import CodeElement
from gcd.scorer import CodeElementScorer

class BaseGithubCodeSearcher(ABC):
    def __init__(
        self,
        github_token: str | None = None,
        scorer: CodeElementScorer | None = None,
        debug: bool = False,
        max_files: int = 100,
        max_results: int = 50,
    ):
        self.github_token = os.getenv("GITHUB_ACCESS_TOKEN", github_token)
        assert self.github_token, "GitHub token must be provided"

        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.scorer = scorer
        self.debug = bool(debug)
        self.max_files = max_files
        self.max_results = max_results

    @property
    def headers(self) -> dict[str, str]:
        """Return headers for GitHub API requests."""
        return {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get_file_content(self, owner: str, repo: str, file_path: str) -> str:
        """Fetch file content from GitHub API."""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"  # noqa

        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("encoding") == "base64":
                import base64
                content = base64.b64decode(data["content"]).decode("utf-8")
                return content
            else:
                return data.get("content", "")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {file_path}: {e}")
            return ""
    
    def check_repo_access(self, owner: str, repo: str) -> bool:
        """Check if repository exists and is accessible."""
        try:
            response = self.session.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                timeout=10
            )
            if response.status_code == 200:
                repo_data = response.json()
                if self.debug:
                    logger.info(f"Repository {owner}/{repo} is accessible. Size: {repo_data.get('size', 0)} KB")
                return True
            elif response.status_code == 404:
                logger.error(f"Repository {owner}/{repo} not found or not accessible")
                return False
            else:
                logger.error(f"Error accessing repository: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error checking repo access: {e}")
            return False

    @abstractmethod
    def search_python_files(
        self,
        owner: str,
        repo: str,
        query: str = "",
        max_files: int = 50,
    ) -> list[dict]:
        """Search for Python files in the repository using GitHub API."""
        raise NotImplementedError()

    def parse_github_url(self, url: str) -> tuple[str, str]:
        """Parse GitHub URL to extract owner and repo name."""
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise ValueError("Invalid GitHub URL format")
        return path_parts[0], path_parts[1]
    
    def extract_code_elements(
        self,
        code: str,
        file_path: str,
    ) -> list[CodeElement]:
        """Extract functions and classes from Python code using AST."""
        elements = []
        code_lines = code.split("\n")

        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(
                    node,
                    ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
                ):
                    element_type = (
                        "function"
                        if isinstance(
                            node,
                            ast.FunctionDef | ast.AsyncFunctionDef,
                        )
                        else "class"
                    )

                    # Extract docstring
                    docstring = ""
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)
                    ):
                        docstring = node.body[0].value.value

                    # Extract function signature with type hints
                    signature = ""
                    if isinstance(
                        node,
                        ast.FunctionDef | ast.AsyncFunctionDef,
                    ):
                        args = []
                        for arg in node.args.args:
                            arg_str = arg.arg
                            if arg.annotation:
                                try:
                                    arg_str += f": {ast.unparse(arg.annotation)}"  # noqa
                                except:  # noqa
                                    pass
                            args.append(arg_str)

                        return_annotation = ""
                        if node.returns:
                            try:
                                return_annotation = f" -> {ast.unparse(node.returns)}"  # noqa
                            except:  # noqa
                                pass

                        async_prefix = (
                            "async " if isinstance(node, ast.AsyncFunctionDef) else ""  # noqa
                        )
                        signature = f"{async_prefix}def {node.name}({', '.join(args)}){return_annotation}"  # noqa
                    else:
                        # Handle class inheritance
                        bases = []
                        if node.bases:
                            for base in node.bases:
                                try:
                                    bases.append(ast.unparse(base))
                                except:  # noqa
                                    bases.append("Unknown")
                        inheritance = f"({', '.join(bases)})" if bases else ""
                        signature = f"class {node.name}{inheritance}"

                    # Extract the actual code
                    start_line = node.lineno - 1  # AST uses 1-based indexing
                    end_line = (
                        node.end_lineno
                        if hasattr(node, "end_lineno") and node.end_lineno
                        else start_line + 1
                    )

                    # Get the full code block
                    element_code = ""
                    if start_line < len(code_lines):
                        # Find the actual end by looking for proper indentation
                        base_indent = len(code_lines[start_line]) - len(
                            code_lines[start_line].lstrip(),
                        )
                        actual_end = end_line

                        # Scan forward to find the actual end of the function/class # noqa
                        for i in range(end_line, len(code_lines)):
                            line = code_lines[i]
                            if line.strip():  # Non-empty line
                                line_indent = len(line) - len(line.lstrip())
                                if (
                                    line_indent <= base_indent
                                    and not line.lstrip().startswith(
                                        ("@", "#"),
                                    )
                                ):
                                    actual_end = i
                                    break
                            actual_end = i + 1

                        element_code = "\n".join(
                            code_lines[start_line:actual_end],
                        )

                    element = CodeElement(
                        name=node.name,
                        type=element_type,
                        line_number=node.lineno,
                        file_path=file_path,
                        docstring=docstring,
                        signature=signature,
                        code=element_code,
                    )
                    elements.append(element)

        except SyntaxError as e:
            logger.error(f"Syntax error in {file_path}: {e}")
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")

        return elements

    def score_element(self, element: CodeElement, query: str) -> float:
        """Score how well an element matches the query."""
        query_lower = query.lower()
        score = 0.0

        # Name matching (highest weight)
        if query_lower in element.name.lower():
            score += 10.0
            if element.name.lower().startswith(query_lower):
                score += 5.0
            if element.name.lower() == query_lower:
                score += 10.0

        # Docstring matching
        if element.docstring and query_lower in element.docstring.lower():
            score += 3.0

        # Signature matching
        if query_lower in element.signature.lower():
            score += 2.0

        # File path matching
        if query_lower in element.file_path.lower():
            score += 1.0

        # Bonus for exact word matches
        query_words = query_lower.split()
        for word in query_words:
            if word in element.name.lower().split("_"):
                score += 2.0

        return score

    def search_code_elements(
        self,
        repo_url: str,
        query: str,
        top_k: int = 25,
        max_files: int = 50,
        weights: dict[str, float] | None = None,
    ) -> list[CodeElement]:
        """Search for code elements matching the query."""
        query = query.strip()
        if not query:
            logger.warning("Empty search query provided")
            return []
        top_k = min(top_k, self.max_results)
        owner, repo = self.parse_github_url(repo_url)

        logger.info(f"Searching in {owner}/{repo}")

        # Search for relevant Python files
        files = self.search_python_files(owner, repo, query, max_files)
        logger.info(f"Found {len(files)} Python files to analyze")

        all_elements = []

        for i, file_info in enumerate(files):
            file_path = file_info["path"]
            logger.info(f"Analyzing [{i + 1}/{len(files)}]: {file_path}")

            # Get file content
            content = self.get_file_content(owner, repo, file_path)
            if not content:
                continue

            # Extract code elements
            elements = self.extract_code_elements(content, file_path)

            # Score elements based on query
            for element in elements:
                element.score = self.score_element(element, query)
                if self.scorer:
                    element.score = self.scorer.score_element(
                        element,
                        query,
                        weights=weights,
                    )
                if element.score > 0:
                    all_elements.append(element)

        # Sort by score and return top results
        all_elements.sort(key=lambda x: x.score, reverse=True)
        return all_elements[:top_k]

    def print_results(
        self,
        elements: list[CodeElement],
        show_code: bool = True,
    ):
        """Print search results in a formatted way."""
        if not elements:
            print("No matching functions or classes found.")
            return

        print(f"\nTop {len(elements)} matching code elements:")
        print("=" * 80)

        for i, element in enumerate(elements, 1):
            print(f"\n{i}. {element.type.upper()}: {element.name}")
            print(f"   File: {element.file_path}:{element.line_number}")
            print(f"   Signature: {element.signature}")
            print(f"   Score: {element.score:.3f}")

            if element.docstring:
                # Truncate long docstrings
                doc_preview = element.docstring[:150]
                if len(element.docstring) > 150:
                    doc_preview += "..."
                print(f"   Docstring: {doc_preview}")

            if show_code and element.code:
                print("   Code:")
                # Indent the code for better readability
                code_lines = element.code.split("\n")
                for line in code_lines[:20]:  # Show first 20 lines
                    print(f"     {line}")
                if len(code_lines) > 20:
                    print(f"     ... ({len(code_lines) - 20} more lines)")

            print("-" * 80)

    def export_results(self, elements: list[CodeElement], output_file: str):
        """Export results to JSON file."""
        results = []
        for element in elements:
            results.append(
                {
                    "name": element.name,
                    "type": element.type,
                    "line_number": element.line_number,
                    "file_path": element.file_path,
                    "signature": element.signature,
                    "docstring": element.docstring,
                    "code": element.code,
                    "score": element.score,
                },
            )

        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results exported to {output_file}")

class DefaultGitHubCodeSearcher(BaseGithubCodeSearcher):
    def search_python_files(
        self,
        owner: str,
        repo: str,
        query: str = "",
        max_files: int = 50,
    ) -> list[dict]:
        """Search for Python files in the repository using GitHub API."""
        # First check if repo is accessible
        if not self.check_repo_access(owner, repo):
            logger.error(f"Cannot access repository {owner}/{repo}")
            return []
        
        search_query = f"repo:{owner}/{repo} extension:py"
        if query:
            search_query += f" {query}"

        if self.debug:
            logger.debug(search_query)
        url = "https://api.github.com/search/code"
        params = {
            "q": search_query,
            "per_page": min(max_files, self.max_files),
            "sort": "indexed",
        }

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching files: {e}")
            return []

class RateLimitedGitHubCodeSearcher(BaseGithubCodeSearcher):
    def __init__(
        self,
        github_token: str | None = None,
        scorer: CodeElementScorer | None = None,
        max_files: int = 100,
        max_results: int = 50,
        min_request_interval: float = 6.1,
        debug: bool = False,
    ) -> None:
        super().__init__(
            github_token=github_token,
            scorer=scorer,
            max_files=max_files,
            max_results=max_results,  
            debug=debug,
        )
        self.min_request_interval=min_request_interval
        self.last_request_time = 0

    def _wait_for_rate_limit(self):
        """Ensure we don't exceed the code search rate limit."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last
            if self.debug:
                logger.info(f"Rate limiting: waiting {wait_time:.1f} seconds")
            time.sleep(wait_time)
        
        self.last_request_time = time.time()


    def _search_python_files(
        self,
        owner: str,
        repo: str,
        query: str = "",
        max_files: int = 50,
    ) -> list[dict]:
        """Search for Python files in the repository using GitHub API."""
        
        # First check if repo is accessible
        if not self.check_repo_access(owner, repo):
            logger.error(f"Cannot access repository {owner}/{repo}")
            return []
        
        # Build search query
        search_query = f"repo:{owner}/{repo} extension:py"
        if query.strip():
            # Clean and escape the query
            clean_query = query.strip()
            # For phrases with spaces, use quotes
            if ' ' in clean_query and not (clean_query.startswith('"') and clean_query.endswith('"')):
                search_query += f' "{clean_query}"'
            else:
                search_query += f" {clean_query}"

        url = "https://api.github.com/search/code"
        params = {
            "q": search_query,
            "per_page": min(max_files, min(self.max_files, 100)),  # GitHub max is 100
            # Remove 'sort' parameter - it's deprecated for code search
        }

        if self.debug:
            logger.info(f"Searching with query: {search_query}")
            logger.info(f"Request params: {params}")

        try:
            # Apply rate limiting
            self._wait_for_rate_limit()
            
            response = self.session.get(url, params=params, timeout=30)
            
            # Log response details for debugging
            if self.debug:
                logger.info(f"Response status: {response.status_code}")
                logger.info(f"Rate limit remaining: {response.headers.get('X-RateLimit-Remaining', 'unknown')}")
                logger.info(f"Rate limit reset: {response.headers.get('X-RateLimit-Reset', 'unknown')}")

            # Handle rate limiting specifically
            if response.status_code == 403:
                error_msg = response.json().get('message', '') if response.content else ''
                if 'rate limit exceeded' in error_msg.lower():
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    current_time = int(time.time())
                    wait_time = max(0, reset_time - current_time + 1)
                    logger.warning(f"Rate limit exceeded. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    return []
                else:
                    logger.error(f"Access forbidden: {error_msg}")
                    return []
            
            # Handle other HTTP errors
            if response.status_code == 422:
                error_msg = response.json().get('message', '') if response.content else ''
                logger.error(f"Invalid search query: {error_msg}")
                logger.error(f"Query was: {search_query}")
                return []
                
            response.raise_for_status()
            data = response.json()
            
            items = data.get("items", [])
            total_count = data.get("total_count", 0)
            
            if self.debug:
                logger.info(f"Found {len(items)} files (total available: {total_count})")
                if items:
                    logger.info(f"Sample file: {items[0].get('path', 'unknown')}")
            
            return items
            
        except requests.exceptions.Timeout:
            logger.error("Request timed out")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching files: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                try:
                    error_data = e.response.json()
                    logger.error(f"Error details: {error_data}")
                except:
                    logger.error(f"Response text: {e.response.text[:500]}")
            return []
    
    def _fallback_1(
        self,
        owner: str,
        repo: str,
        query: str,
        max_files: int,
    ) -> list[dict]:
        """Fallback strategy 1: Search without content query."""
        logger.info("Fallback: Searching without content query")
        results = []
        query = query.strip()
        # empty search first
        results = self._search_python_files(owner, repo, "", max_files)
        if not results:
            return []
        # Filter results locally based on query
        filtered_results = []
        query_lower = query.lower()

        # check if query in the results
        for file in results:
            file_path = file.get('path', '').lower()
            if query_lower in file_path or query_lower in file.get('name', '').lower():
                filtered_results.append(file)
        return filtered_results or results
    
    def _fallback_2(
        self,
        owner: str,
        repo: str,
        query: str,
        max_files,
    ) -> list[dict]:
        """Fallback strategy 2: Use Contents API to list Python files."""
        logger.info("Fallback: Using Contents API")
        results = []
        try:
            contents_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
            response = self.session.get(contents_url, timeout=10)
            if response.status_code == 200:
                contents = response.json()
                results = []
                for item in contents:
                    if item.get('name', '').endswith('.py'):
                        # Convert to code search format
                        results.append({
                            'name': item['name'],
                            'path': item['path'],
                            'url': item.get('html_url', ''),
                            'sha': item.get('sha', ''),
                        })
        except Exception as e:
            logger.error(f"Contents API fallback failed: {e}")
        return results

    def search_python_files(
        self,
        owner: str,
        repo: str,
        query: str = "",
        max_files: int = 50,
    ) -> list[dict]:
        """Search with fallback strategies if initial search fails."""
        query = query.strip()
        results = []

        # waterfall
        for _fn in [self._search_python_files, self._fallback_1, self._fallback_2]:
            results = _fn(owner, repo, query, max_files)
            if self.debug:
                logger.debug(f"Results from {_fn.__name__}: {len(results)} files found")
            if results:
                break
        return results




# class GitHubCodeSearcher3:
#     def __init__(
#         self,
#         github_token: str | None = None,
#         scorer: CodeElementScorer | None = None,
#         debug: bool = False,
#         max_files: int = 1000,  # Increased since we're not limited by API
#         max_results: int = 50,
#         use_local_clone: bool = True,
#         clone_timeout: int = 300,  # 5 minutes timeout for cloning
#     ):
#         self.github_token = os.getenv("GITHUB_ACCESS_TOKEN", github_token)
#         self.session = requests.Session()
#         if self.github_token:
#             self.session.headers.update(self.headers)
        
#         self.scorer = scorer
#         self.debug = bool(debug)
#         self.max_files = max_files
#         self.max_results = max_results
#         self.use_local_clone = use_local_clone
#         self.clone_timeout = clone_timeout
#         self._clone_cache = {}  # Cache cloned repos to avoid re-cloning

#     @property
#     def headers(self) -> dict[str, str]:
#         """Return headers for GitHub API requests."""
#         return {
#             "Authorization": f"token {self.github_token}",
#             "Accept": "application/vnd.github.v3+json",
#             "User-Agent": "GitHubCodeSearcher/2.0",
#         }

#     def parse_github_url(self, url: str) -> tuple[str, str]:
#         """Parse GitHub URL to extract owner and repo name."""
#         parsed = urlparse(url)
#         path_parts = parsed.path.strip("/").split("/")
#         if len(path_parts) < 2:
#             raise ValueError("Invalid GitHub URL format")
#         return path_parts[0], path_parts[1]

#     def get_clone_url(self, owner: str, repo: str, use_https: bool = True) -> str:
#         """Get the appropriate clone URL."""
#         if use_https:
#             if self.github_token:
#                 return f"https://{self.github_token}@github.com/{owner}/{repo}.git"
#             else:
#                 return f"https://github.com/{owner}/{repo}.git"
#         else:
#             return f"git@github.com:{owner}/{repo}.git"

#     def clone_repository(self, repo_url: str, target_dir: str, shallow: bool = True) -> bool:
#         """Clone repository to target directory with timeout."""
#         owner, repo = self.parse_github_url(repo_url)
#         clone_url = self.get_clone_url(owner, repo)
        
#         # Build git clone command
#         cmd = ["git", "clone"]
#         if shallow:
#             cmd.extend(["--depth", "1"])  # Shallow clone for speed
#         cmd.extend([clone_url, target_dir])
        
#         logger.info(f"Cloning {owner}/{repo} to {target_dir}")
        
#         try:
#             # Use subprocess with timeout
#             result = subprocess.run(
#                 cmd,
#                 capture_output=True,
#                 text=True,
#                 timeout=self.clone_timeout,
#                 cwd=os.path.dirname(target_dir) if os.path.dirname(target_dir) else None
#             )
            
#             if result.returncode == 0:
#                 logger.info(f"Successfully cloned {owner}/{repo}")
#                 return True
#             else:
#                 logger.error(f"Git clone failed: {result.stderr}")
#                 # Try without token (for public repos)
#                 if self.github_token and "authentication failed" in result.stderr.lower():
#                     logger.info("Retrying without token for public repo")
#                     public_url = f"https://github.com/{owner}/{repo}.git"
#                     cmd[-2] = public_url
#                     result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.clone_timeout)
#                     if result.returncode == 0:
#                         logger.info(f"Successfully cloned {owner}/{repo} (public)")
#                         return True
#                 return False
                
#         except subprocess.TimeoutExpired:
#             logger.error(f"Clone timeout after {self.clone_timeout} seconds")
#             return False
#         except FileNotFoundError:
#             logger.error("Git not found. Please install git.")
#             return False
#         except Exception as e:
#             logger.error(f"Clone error: {e}")
#             return False

#     def find_python_files(self, repo_path: str, query: str = "") -> list[str]:
#         """Find Python files in the cloned repository."""
#         python_files = []
#         repo_path = Path(repo_path)
        
#         # Skip common directories that usually don't contain relevant code
#         skip_dirs = {
#             '.git', '__pycache__', '.pytest_cache', 'node_modules', 
#             '.venv', 'venv', 'env', '.env', 'dist', 'build', '.tox',
#             '.coverage', 'htmlcov', '.mypy_cache', 'site-packages',
#             'tests', 'test', 'docs', 'doc', 'examples', 'example'
#         }
        
#         try:
#             for py_file in repo_path.rglob("*.py"):
#                 # Skip files in excluded directories
#                 if any(part in skip_dirs for part in py_file.parts):
#                     continue
                    
#                 # Skip very large files (>1MB) to avoid memory issues
#                 try:
#                     if py_file.stat().st_size > 1024 * 1024:
#                         continue
#                 except (OSError, FileNotFoundError):
#                     continue
                
#                 # Convert to relative path for consistent handling
#                 rel_path = py_file.relative_to(repo_path)
#                 python_files.append(str(rel_path))
        
#         except Exception as e:
#             logger.error(f"Error finding Python files: {e}")
        
#         # Sort by relevance if query is provided
#         if query and python_files:
#             query_lower = query.lower()
#             # Prioritize files whose names contain the query
#             python_files.sort(key=lambda f: (
#                 query_lower not in f.lower(),  # Files matching query first
#                 f.count('/'),  # Prefer files in root over deep nested
#                 f  # Alphabetical as final tie-breaker
#             ))
        
#         logger.info(f"Found {len(python_files)} Python files")
#         return python_files[:self.max_files]

#     def read_file_content(self, file_path: Path) -> str:
#         """Read file content with encoding detection."""
#         try:
#             # Try UTF-8 first
#             return file_path.read_text(encoding='utf-8')
#         except UnicodeDecodeError:
#             try:
#                 # Fallback to latin-1
#                 return file_path.read_text(encoding='latin-1')
#             except Exception as e:
#                 logger.error(f"Could not read {file_path}: {e}")
#                 return ""

#     def extract_code_elements(
#         self,
#         code: str,
#         file_path: str,
#     ) -> list[CodeElement]:
#         """Extract functions and classes from Python code using AST."""
#         elements = []
#         code_lines = code.split("\n")

#         try:
#             tree = ast.parse(code)

#             for node in ast.walk(tree):
#                 if isinstance(
#                     node,
#                     ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
#                 ):
#                     element_type = (
#                         "function"
#                         if isinstance(
#                             node,
#                             ast.FunctionDef | ast.AsyncFunctionDef,
#                         )
#                         else "class"
#                     )

#                     # Extract docstring
#                     docstring = ""
#                     if (
#                         node.body
#                         and isinstance(node.body[0], ast.Expr)
#                         and isinstance(node.body[0].value, ast.Constant)
#                         and isinstance(node.body[0].value.value, str)
#                     ):
#                         docstring = node.body[0].value.value

#                     # Extract function signature with type hints
#                     signature = ""
#                     if isinstance(
#                         node,
#                         ast.FunctionDef | ast.AsyncFunctionDef,
#                     ):
#                         args = []
#                         for arg in node.args.args:
#                             arg_str = arg.arg
#                             if arg.annotation:
#                                 try:
#                                     arg_str += f": {ast.unparse(arg.annotation)}"
#                                 except:
#                                     pass
#                             args.append(arg_str)

#                         return_annotation = ""
#                         if node.returns:
#                             try:
#                                 return_annotation = f" -> {ast.unparse(node.returns)}"
#                             except:
#                                 pass

#                         async_prefix = (
#                             "async " if isinstance(node, ast.AsyncFunctionDef) else ""
#                         )
#                         signature = f"{async_prefix}def {node.name}({', '.join(args)}){return_annotation}"
#                     else:
#                         # Handle class inheritance
#                         bases = []
#                         if node.bases:
#                             for base in node.bases:
#                                 try:
#                                     bases.append(ast.unparse(base))
#                                 except:
#                                     bases.append("Unknown")
#                         inheritance = f"({', '.join(bases)})" if bases else ""
#                         signature = f"class {node.name}{inheritance}"

#                     # Extract the actual code
#                     start_line = node.lineno - 1  # AST uses 1-based indexing
#                     end_line = (
#                         node.end_lineno
#                         if hasattr(node, "end_lineno") and node.end_lineno
#                         else start_line + 1
#                     )

#                     # Get the full code block
#                     element_code = ""
#                     if start_line < len(code_lines):
#                         # Find the actual end by looking for proper indentation
#                         base_indent = len(code_lines[start_line]) - len(
#                             code_lines[start_line].lstrip(),
#                         )
#                         actual_end = end_line

#                         # Scan forward to find the actual end of the function/class
#                         for i in range(end_line, len(code_lines)):
#                             line = code_lines[i]
#                             if line.strip():  # Non-empty line
#                                 line_indent = len(line) - len(line.lstrip())
#                                 if (
#                                     line_indent <= base_indent
#                                     and not line.lstrip().startswith(
#                                         ("@", "#"),
#                                     )
#                                 ):
#                                     actual_end = i
#                                     break
#                             actual_end = i + 1

#                         element_code = "\n".join(
#                             code_lines[start_line:actual_end],
#                         )

#                     element = CodeElement(
#                         name=node.name,
#                         type=element_type,
#                         line_number=node.lineno,
#                         file_path=file_path,
#                         docstring=docstring,
#                         signature=signature,
#                         code=element_code,
#                     )
#                     elements.append(element)

#         except SyntaxError as e:
#             logger.debug(f"Syntax error in {file_path}: {e}")
#         except Exception as e:
#             logger.error(f"Error parsing {file_path}: {e}")

#         return elements

#     def score_element(self, element: CodeElement, query: str) -> float:
#         """Score how well an element matches the query."""
#         query_lower = query.lower()
#         score = 0.0

#         # Name matching (highest weight)
#         if query_lower in element.name.lower():
#             score += 10.0
#             if element.name.lower().startswith(query_lower):
#                 score += 5.0
#             if element.name.lower() == query_lower:
#                 score += 10.0

#         # Docstring matching
#         if element.docstring and query_lower in element.docstring.lower():
#             score += 3.0

#         # Signature matching
#         if query_lower in element.signature.lower():
#             score += 2.0

#         # File path matching
#         if query_lower in element.file_path.lower():
#             score += 1.0

#         # Code content matching
#         if element.code and query_lower in element.code.lower():
#             score += 2.0

#         # Bonus for exact word matches
#         query_words = query_lower.split()
#         for word in query_words:
#             if word in element.name.lower().split("_"):
#                 score += 2.0

#         return score

#     def search_code_elements_local(
#         self,
#         repo_path: str,
#         query: str,
#         top_k: int = 25,
#         weights: dict[str, float] | None = None,
#     ) -> list[CodeElement]:
#         """Search for code elements in a local repository."""
#         repo_path = Path(repo_path)
#         all_elements = []
        
#         # Find Python files
#         python_files = self.find_python_files(repo_path, query)
        
#         if not python_files:
#             logger.warning("No Python files found in repository")
#             return []
        
#         logger.info(f"Analyzing {len(python_files)} Python files")
        
#         for i, file_path in enumerate(python_files):
#             if i % 50 == 0:  # Progress logging
#                 logger.info(f"Progress: {i}/{len(python_files)} files processed")
            
#             full_path = repo_path / file_path
            
#             # Read file content
#             content = self.read_file_content(full_path)
#             if not content:
#                 continue
                
#             # Extract code elements
#             elements = self.extract_code_elements(content, file_path)
            
#             # Score elements
#             for element in elements:
#                 element.score = self.score_element(element, query)
#                 if self.scorer:
#                     element.score = self.scorer.score_element(
#                         element,
#                         query,
#                         weights=weights,
#                     )
#                 if element.score > 0:
#                     all_elements.append(element)
        
#         # Sort by score and return top results
#         all_elements.sort(key=lambda x: x.score, reverse=True)
#         logger.info(f"Found {len(all_elements)} matching code elements")
#         return all_elements[:top_k]

#     def search_code_elements(
#         self,
#         repo_url: str,
#         query: str,
#         top_k: int = 25,
#         max_files: int = 50,
#         weights: dict[str, float] | None = None,
#         force_api: bool = False,
#     ) -> list[CodeElement]:
#         """Search for code elements matching the query."""
#         query = query.strip()
#         if not query:
#             logger.warning("Empty search query provided")
#             return []
            
#         top_k = min(top_k, self.max_results)
#         owner, repo = self.parse_github_url(repo_url)
#         repo_key = f"{owner}/{repo}"

#         # Use local clone method if enabled and not forced to use API
#         if self.use_local_clone and not force_api:
#             return self._search_with_local_clone(repo_url, query, top_k, weights)
#         else:
#             # Fallback to API method (your original implementation)
#             return self._search_with_api(repo_url, query, top_k, max_files, weights)

#     def _search_with_local_clone(
#         self,
#         repo_url: str,
#         query: str,
#         top_k: int,
#         weights: dict[str, float] | None = None,
#     ) -> list[CodeElement]:
#         """Search using local clone approach."""
#         owner, repo = self.parse_github_url(repo_url)
#         repo_key = f"{owner}/{repo}"
        
#         # Check if we already have this repo cloned
#         if repo_key in self._clone_cache:
#             clone_dir = self._clone_cache[repo_key]
#             if os.path.exists(clone_dir):
#                 logger.info(f"Using cached clone at {clone_dir}")
#                 return self.search_code_elements_local(clone_dir, query, top_k, weights)
        
#         # Create temporary directory for clone
#         with tempfile.TemporaryDirectory(prefix=f"github_search_{owner}_{repo}_") as temp_dir:
#             clone_path = os.path.join(temp_dir, repo)
            
#             # Clone repository
#             if not self.clone_repository(repo_url, clone_path):
#                 logger.error("Failed to clone repository, falling back to API")
#                 return self._search_with_api(repo_url, query, top_k, 50, weights)
            
#             # Cache the clone path for this session
#             self._clone_cache[repo_key] = clone_path
            
#             # Search in local repository
#             return self.search_code_elements_local(clone_path, query, top_k, weights)

#     def _search_with_api(
#         self,
#         repo_url: str,
#         query: str,
#         top_k: int,
#         max_files: int,
#         weights: dict[str, float] | None = None,
#     ) -> list[CodeElement]:
#         """Fallback to API-based search (original method)."""
#         # Your original API-based implementation here
#         # This is a simplified version - you can copy your original method
#         logger.warning("API-based search not fully implemented in this version")
#         return []

#     def cleanup_cache(self):
#         """Cleanup cloned repositories."""
#         for repo_key, clone_path in self._clone_cache.items():
#             try:
#                 if os.path.exists(clone_path):
#                     shutil.rmtree(clone_path)
#                     logger.info(f"Cleaned up {repo_key} cache")
#             except Exception as e:
#                 logger.error(f"Error cleaning up {repo_key}: {e}")
#         self._clone_cache.clear()

#     def __del__(self):
#         """Cleanup on destruction."""
#         self.cleanup_cache()

#     def print_results(
#         self,
#         elements: list[CodeElement],
#         show_code: bool = True,
#     ):
#         """Print search results in a formatted way."""
#         if not elements:
#             print("No matching functions or classes found.")
#             return

#         print(f"\nTop {len(elements)} matching code elements:")
#         print("=" * 80)

#         for i, element in enumerate(elements, 1):
#             print(f"\n{i}. {element.type.upper()}: {element.name}")
#             print(f"   File: {element.file_path}:{element.line_number}")
#             print(f"   Signature: {element.signature}")
#             print(f"   Score: {element.score:.3f}")

#             if element.docstring:
#                 # Truncate long docstrings
#                 doc_preview = element.docstring[:150]
#                 if len(element.docstring) > 150:
#                     doc_preview += "..."
#                 print(f"   Docstring: {doc_preview}")

#             if show_code and element.code:
#                 print("   Code:")
#                 # Indent the code for better readability
#                 code_lines = element.code.split("\n")
#                 for line in code_lines[:20]:  # Show first 20 lines
#                     print(f"     {line}")
#                 if len(code_lines) > 20:
#                     print(f"     ... ({len(code_lines) - 20} more lines)")

#             print("-" * 80)

#     def export_results(self, elements: list[CodeElement], output_file: str):
#         """Export results to JSON file."""
#         results = []
#         for element in elements:
#             results.append(
#                 {
#                     "name": element.name,
#                     "type": element.type,
#                     "line_number": element.line_number,
#                     "file_path": element.file_path,
#                     "signature": element.signature,
#                     "docstring": element.docstring,
#                     "code": element.code,
#                     "score": element.score,
#                 },
#             )

#         with open(output_file, "w") as f:
#             json.dump(results, f, indent=2)
#         logger.info(f"Results exported to {output_file}")
