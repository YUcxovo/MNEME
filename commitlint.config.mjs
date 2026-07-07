export default {
    extends: ["@commitlint/config-conventional"],
    rules: {
        "type-enum": [
            2,
            "always",
            [
                "feat",
                "fix",
                "refactor",
                "docs",
                "test",
                "chore",
                "ci",
                "perf",
                "style",
                "build",
                "revert",
            ],
        ],
        "subject-case": [0],
        "header-max-length": [2, "always", 72],
    },
};
