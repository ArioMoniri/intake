module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    // The delivery model puts issue ids (INT-xxx) in subjects; the default
    // subject-case rule rejects the uppercase id. Everything else stays.
    "subject-case": [0],
  },
};
