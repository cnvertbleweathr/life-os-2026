from pixela_client import create_graph

GRAPHS = [
    ("meditation", "Meditation"),
    ("pushups100", "100 Pushups"),
    ("nonfiction10", "10 Pages Non-Fiction"),
    ("fiction10", "10 Pages Fiction"),
]

for gid, name in GRAPHS:
    print(gid, create_graph(gid, name))
