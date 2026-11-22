# STAAD.Pro check of the SettleFrame example frame

Goal: show that SettleFrame's frame results match a commercial program.
Model: 3 bays x 6 m, 2 stories (4.0 m, 3.5 m), fixed bases, E = 25 GPa,
columns 0.4 x 0.4 m, beams 0.3 wide x 0.6 deep. Units kN and m.

Load cases in the input file
1. Dead load D: 30 kN/m on floor beams, 20 kN/m on roof beams
2. Live load L: 12 kN/m on floor beams, 5 kN/m on roof beams
3. Settlement S: footing settlements after 30 years from SettleFrame (coupled)
   F1 7.01 mm, F2 20.76 mm, F3 24.61 mm, F4 19.46 mm (SUPPORT DISPLACEMENT LOAD)
4. Combination D + 0.3L + S (the sustained load plus settlement)

## Steps
1. Open STAAD.Pro. Use File > Open and pick `example_frame_check.std` in this folder.
   (Or start a new model, open the STAAD Editor, paste the whole file, and save.)
2. Look at the model: 12 joints, 14 members, 4 fixed supports at the bottom.
   Members 1-4 are the first-story columns (F1 to F4), 5-8 the second-story columns,
   9-11 the first-floor beams, 12-14 the roof beams.
3. Run the analysis (Analysis and Design > Run Analysis; in older versions Analyze > Run Analysis).
   When it finishes, open the output file. Check that it reports 0 errors.
   STAAD saves the output as `example_frame_check.anl` next to the .std file. Keep it in this folder.
4. In the output file, find SUPPORT REACTIONS (FY at joints 1-4 for loads 1-4)
   and MEMBER END FORCES (MZ at both ends of members 1, 5, 9 and 11 for loads 1 and 3).
5. Compare with `settleframe_values.csv` (SettleFrame's numbers). Compare magnitudes;
   STAAD reports end moments in member local axes, like SettleFrame, so signs should also match.
6. Optional: delete the `SET SHEAR` line, run again, and note how much the settlement
   moments drop when shear deformation is included (a good point for the discussion).

What to expect: with SET SHEAR, differences should be well under 0.5%.
The load 4 reactions (about 223.8, 270.4, 281.4, 216.2 kN) should equal SettleFrame's
coupled footing loads at 30 years. That checks the coupling equation P = P0 - C s.

For the slides: a screenshot of the STAAD model with the bending moment diagram for load 3
(Postprocessing, beam results, MZ) is useful.
