from data_loader import _norm_component_name

def run_tests() -> None:
    """Basic sanity tests for _norm_component_name."""
    
    # Define a dictionary of test cases.
    # The key is the 'input' string, and the value is the 'expected' normalized output.
    cases = {
        "Colon.Suis.D4": "colon suis",         # Case 1: Dots and dosage
        "Colon suis": "colon suis",            # Case 2: Standard format
        "Avena.sativa D10": "avena sativa",    # Case 3: Mixed separators
        "  Avena_sativa  d4 ": "avena sativa", # Case 4: Extra spaces and underscore
        "Random": "random",                    # Case 5: Simple word
        "Chelidonium.majus": "chelidonium majus", # Case 6: Standard format
        "Citrullus.colocynthis.": "citrullus colocynthis", # Case 7: Trailing dot
        "Hepar.comp.Ampoules..Bulk.mat.52324.": "hepar comp ampoules bulk mat 52324", # Case 8: Trailing dot
        "Hepeel.ampoule.solution..Bulk": "hepeel ampoule solution bulk", # Case 9: Trailing dot
        "Myristica.fragrans.": "myristica fragrans", # Case 10: Trailing dot

    }

    # Iterate through each input and expected result in the dictionary
    for inp, expected in cases.items():
        # Call the function with the input to get the actual result
        out = _norm_component_name(inp)
        
        # Print the current test case to the console for visibility
        print(f"Input: {inp!r} -> Output: {out!r} (expected: {expected!r})")
        
        # Verify if the actual output matches the expected output.
        # If they do not match, the program will stop and show an error message.
        assert out == expected, f"Mismatch for {inp!r}: got {out!r}, expected {expected!r}"

    # If the loop finishes without any errors, print a success message
    print("All _norm_component_name tests passed!")

# Entry point: Run the run_tests function only if this script is executed directly
if __name__ == "__main__":
    run_tests()