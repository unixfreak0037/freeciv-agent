"""
FreeCiv AI Client Test Suite

This package contains tests for the FreeCiv AI client implementation.

Directory Structure:
    unit/        - Pure unit tests for individual functions (fast, no I/O)
    async/       - Async tests with mocked StreamReader/StreamWriter
    integration/ - Integration tests across multiple modules

Running Tests:
    # Run all tests
    pytest

    # Run specific test directory
    pytest tests/unit
    pytest tests/async
    pytest tests/integration

    # Run with coverage
    pytest --cov=fc_client --cov-report=html

    # Run tests matching a pattern
    pytest -k test_name_pattern

    # Run with specific markers
    pytest -m unit
    pytest -m async_test
    pytest -m integration

Test Markers:
    @pytest.mark.unit         - Fast unit tests (no I/O)
    @pytest.mark.async_test   - Async tests with mocked I/O
    @pytest.mark.integration  - Integration tests (cross-module)
    @pytest.mark.network      - Tests requiring network mocking
    @pytest.mark.slow         - Slow-running tests

Fixtures:
    Shared fixtures are defined in conftest.py and include:
    - Mock network streams (mock_stream_reader, mock_stream_writer)
    - Component instances (delta_cache, game_state, freeciv_client)
    - Sample packet data (sample_join_reply_success, sample_chat_msg_payload)
    - Utility helpers (packet_builder)

Delta Protocol Testing:
    For comprehensive testing strategies for delta protocol implementation,
    see the "Testing Strategy" section in DELTA_PROTOCOL.md, which includes:
    - Unit tests for bitvector operations (byte order, size calculation, bit masking)
    - Integration tests for cache population and delta decoding
    - Boolean header folding verification
    - Property-based tests for random field combinations
    - Performance tests for bandwidth savings measurement
    - Edge case handling (empty bitvectors, cache misses, first packets)
"""
