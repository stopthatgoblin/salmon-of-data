export interface NIElectionPartyRecord {
    Election: string;
    Year: number;
    Type: string; // "Assembly" | "Westminster" | "Local" | "European" | "Constitutional Convention" | "Forum"
    Contested: number; // 1 or 0
    Party: string;
    Category: string; // "Nationalist" | "Unionist" | "Other"
    Votes: number;
    TotalVotesElection: number;
    VoteShare: number;
}

export interface NIElectionCategoryRecord {
    Election: string;
    Year: number;
    Type: string;
    Contested: number;
    Category: string; // "Nationalist" | "Unionist" | "Other"
    Votes: number;
    TotalVotesElection: number;
    VoteShare: number;
}

export interface NIPartyColors {
    [key: string]: string;
}

export interface NICommunityColors {
    Unionist: string;
    Nationalist: string;
    Other: string;
    [key: string]: string;
}
