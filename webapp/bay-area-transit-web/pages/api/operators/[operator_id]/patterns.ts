// Next.js API route support: https://nextjs.org/docs/api-routes/introduction
import type { NextApiRequest, NextApiResponse } from 'next'

import { Pattern, Direction, Stop } from '../../../../types'
import { getLines } from './lines/index'


const axios = require('axios').default;

const KEY = process.env.API_KEY;
const BASE_URL = process.env.BASE_URL;
const API_PATH = process.env.API_PATH;

export type PatternsResponse = {
    [key: string]: Pattern[]
}

export default async function handler(
    req: NextApiRequest,
    res: NextApiResponse<PatternsResponse>
) {
    // get the operators!


    let pRes: PatternsResponse = {};

    let { operator_id, start_stop, end_stop } = req.query;

    if (operator_id instanceof Array) operator_id = operator_id[0]

    try {
        let url = new URL(API_PATH + '/stops', BASE_URL);
        url.searchParams.append("api_key", KEY!)
        url.searchParams.append("operator_id", operator_id!)
        url.searchParams.append("format", "json")

        const lines = await getLines(operator_id!)
        for (let line of lines) {
            // console.log(line);
            pRes[line.id] = await getPatterns(operator_id!, line.id);
        }

        // if start_stop & end_stop filter everything where start[idx] > end[idx]
        if (!!start_stop && !!end_stop) {
            for (let i = Object.keys(pRes).length-1; i >= 0; i--) {
                let [lineId, patterns] = Object.entries(pRes)[i];
                if (patterns.length === 0) {
                    delete pRes[lineId];
                    continue;
                }
                for (let pattern of patterns) {
                    
                }
            }
        }
    } catch (error) {
        // console.trace(error);
        console.log(error);
        res.status(500).json(JSON.stringify(error));
        return;
    }

    res.status(200).json(pRes);
    return;
}

async function getPatterns(operator_id: string, line_id: string): Promise<Pattern[]> {
    let url = new URL(API_PATH + '/patterns', BASE_URL);
    url.searchParams.append("api_key", KEY!)
    url.searchParams.append("operator_id", operator_id)
    url.searchParams.append("line_id", line_id)
    url.searchParams.append("format", "json")

    let response = await axios.get(url);
    response = response.data;

    const patterns: Pattern[] = [];
    const directions: {[key: string]: Direction}  = {};
    // console.log(JSON.stringify(response))
    for (let dir of response.directions) {
        directions[dir.DirectionId] = {
            id: dir.DirectionId,
            name: dir.Name,
        };
    }

    for (let pattern of response.journeyPatterns) {
        patterns.push({
            id: pattern.serviceJourneyPatternRef,
            name: pattern.Name,
            direction: directions[pattern.DirectionRef],
            stops: pattern.PointsInSequence.TimingPointInJourneyPattern.map((el) => {
                return {
                    id: el.ScheduledStopPointRef,
                    name: el.Name,
               } as Stop})
        } as Pattern);
    }

    return patterns
}