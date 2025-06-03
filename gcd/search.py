from __future__ import annotations

import ast
import json
import os
from urllib.parse import urlparse

import requests
from loguru import logger

from gcd.schema import CodeElement
from gcd.scorer import CodeElementScorer


class GitHubCodeSearcher:
    def __init__(
        self,
        github_token: str | None = None,
        scorer: CodeElementScorer | None = None,
        debug: bool = False,
        max_files: int = 100,
        max_results: int = 25,
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

    def parse_github_url(self, url: str) -> tuple[str, str]:
        """Parse GitHub URL to extract owner and repo name."""
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise ValueError("Invalid GitHub URL format")
        return path_parts[0], path_parts[1]

    def search_python_files(
        self,
        owner: str,
        repo: str,
        query: str = "",
        max_files: int = 50,
    ) -> list[dict]:
        """Search for Python files in the repository using GitHub API."""
        search_query = f"repo:{owner}/{repo} extension:py"
        if query:
            search_query += f" {query}"

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

    def get_file_content(self, owner: str, repo: str, file_path: str) -> str:
        """Fetch file content from GitHub API."""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"

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
                                    arg_str += f": {ast.unparse(arg.annotation)}"
                                except:  # noqa
                                    pass
                            args.append(arg_str)

                        return_annotation = ""
                        if node.returns:
                            try:
                                return_annotation = f" -> {ast.unparse(node.returns)}"
                            except:  # noqa
                                pass

                        async_prefix = (
                            "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                        )
                        signature = f"{async_prefix}def {node.name}({', '.join(args)}){return_annotation}"
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

                        # Scan forward to find the actual end of the function/class
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
        max_files: int = 50,
        max_results: int = 20,
        weights: dict[str, float] | None = None,
    ) -> list[CodeElement]:
        """Search for code elements matching the query."""
        query = query.strip()
        if not query:
            logger.warning("Empty search query provided")
            return []
        max_results = min(max_results, self.max_results)
        owner, repo = self.parse_github_url(repo_url)

        logger.info(f"Searching in {owner}/{repo} for: {query}")

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
        return all_elements[:max_results]

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
