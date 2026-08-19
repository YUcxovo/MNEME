package com.mneme.app.data.network

internal suspend fun MnemeRemoteDataSource.findDigest(
    pageSize: Int = DEFAULT_DIGEST_PAGE_SIZE,
    predicate: (DigestDto) -> Boolean,
): DigestDto? {
    require(pageSize > 0) { "The digest page size must be positive." }
    val visitedCursors = mutableSetOf<String>()
    var cursor: String? = null
    do {
        val page = listDigests(limit = pageSize, cursor = cursor)
        page.items.firstOrNull(predicate)?.let { return it }
        cursor = page.nextCursor?.takeIf(String::isNotBlank)
    } while (cursor != null && visitedCursors.add(cursor))
    return null
}

private const val DEFAULT_DIGEST_PAGE_SIZE = 50
