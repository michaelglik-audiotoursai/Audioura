#!/usr/bin/env python3
"""Restore original Harvard tour content"""

import os
from pathlib import Path

# Original Harvard tour content
harvard_stops = [
    "Harvard Business School by McKim, 1927\n\nOrientation: To best view and appreciate the Harvard Business School building by McKim, visitors should position themselves at the entrance plaza, which offers a grand perspective of the Neoclassical architecture and the surrounding landscape. Take a moment to observe the symmetrical design and the intricate details adorning the exterior of the building.\n\nHarvard Business School, designed by Charles Follen McKim and completed in 1927, is a masterpiece of Neoclassical architecture that embodies the ideals of academic excellence and institutional prestige. The building's grand facade, with its impressive columns, pediments, and ornamental details, reflects the institution's commitment to tradition and innovation in business education.",
    
    "Harvard Yard Historic District\n\nOrientation: Stand at the main entrance to Harvard Yard on Massachusetts Avenue to fully appreciate the historic significance and architectural beauty of this iconic campus centerpiece.\n\nHarvard Yard, established in 1636, represents the heart of Harvard University and one of America's most prestigious educational institutions. The Yard encompasses the oldest part of Harvard's campus, featuring historic brick buildings that have housed generations of students, faculty, and notable alumni who have shaped American history and culture.",
    
    "Widener Library by Horace Trumbauer, 1915\n\nOrientation: Position yourself on the steps of Memorial Church to get the best view of Widener Library's impressive neoclassical facade and understand its central role in Harvard Yard.\n\nWidener Library, designed by Horace Trumbauer and completed in 1915, stands as one of the world's largest university library systems and a monument to learning and scholarship. This magnificent neoclassical structure houses over 3.5 million books and serves as the centerpiece of Harvard's library system.",
    
    "Memorial Hall by William Robert Ware, 1878\n\nOrientation: Approach Memorial Hall from the Cambridge Common side to fully appreciate its Gothic Revival architecture and imposing presence on the Harvard campus.\n\nMemorial Hall, designed by William Robert Ware and completed in 1878, stands as a magnificent example of High Victorian Gothic architecture and serves as a memorial to Harvard alumni who died in the Civil War. This striking building combines educational function with commemorative purpose, housing Sanders Theatre and Annenberg Hall.",
    
    "Harvard Science Center by Josep Lluís Sert, 1972\n\nOrientation: View the Science Center from Oxford Street to appreciate its modernist design and how it contrasts with Harvard's traditional brick architecture.\n\nThe Harvard Science Center, designed by renowned architect Josep Lluís Sert and completed in 1972, represents a bold departure from Harvard's traditional architectural style. This brutalist concrete structure houses lecture halls, laboratories, and the university's main computer facilities.",
    
    "Harvard Art Museums by Renzo Piano, 2014\n\nOrientation: Enter through the Prescott Street entrance to experience the dramatic glass roof and central courtyard that unite the three museum collections.\n\nThe Harvard Art Museums, renovated and expanded by Renzo Piano and completed in 2014, bring together the Fogg, Busch-Reisinger, and Arthur M. Sackler museums under one spectacular glass roof. This architectural achievement creates a unified space for Harvard's world-class art collections.",
    
    "Harvard Stadium by Charles Follen McKim, 1903\n\nOrientation: Approach the stadium from the main entrance on North Harvard Street to appreciate its pioneering reinforced concrete construction and horseshoe design.\n\nHarvard Stadium, designed by Charles Follen McKim and completed in 1903, holds the distinction of being the first reinforced concrete stadium in the world. This revolutionary structure introduced the horseshoe design that would influence stadium architecture for generations.",
    
    "Harvard Medical School Historic Quadrangle\n\nOrientation: Enter through the main gates on Longwood Avenue to experience the formal quadrangle layout and impressive Georgian Revival architecture.\n\nThe Harvard Medical School Historic Quadrangle, completed in the early 20th century, represents one of the finest examples of Georgian Revival architecture in American medical education. The quadrangle design creates a sense of academic community and scholarly tradition.",
    
    "Harvard Law School by Shaw and Hunnewell, 1883\n\nOrientation: View Langdell Hall from the main entrance to appreciate the Richardsonian Romanesque architecture and the building's commanding presence.\n\nHarvard Law School's Langdell Hall, designed by Shaw and Hunnewell and completed in 1883, exemplifies the Richardsonian Romanesque style with its massive stone construction and distinctive architectural features. The building houses one of the world's largest academic law libraries.",
    
    "Harvard Divinity School by Coolidge, Shepley, Bulfinch and Abbott, 1911\n\nOrientation: Approach from Divinity Avenue to see how the Colonial Revival buildings create a peaceful academic enclave separate from the main campus bustle.\n\nHarvard Divinity School, designed by Coolidge, Shepley, Bulfinch and Abbott and completed in 1911, represents a return to Colonial Revival architecture that harmonizes with Harvard's historic character while serving the specialized needs of theological education."
]

# Create tour directory
tour_dir = Path("/app/tours/walking_tour_of_harvard_university_campus_cambridge_massachusetts__walking_original")
tour_dir.mkdir(exist_ok=True)

# Write text files
for i, content in enumerate(harvard_stops, 1):
    text_file = tour_dir / f"audio_{i}.txt"
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(content)

print(f"Created {len(harvard_stops)} stops in {tour_dir}")