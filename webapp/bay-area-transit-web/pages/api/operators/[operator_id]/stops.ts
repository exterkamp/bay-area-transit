// Next.js API route support: https://nextjs.org/docs/api-routes/introduction
import type { NextApiRequest, NextApiResponse } from 'next'

import { Stop, StopExtension, StopType } from '../../../../types'

const axios = require('axios').default;

export default async function handler(
    req: NextApiRequest,
    res: NextApiResponse<Stop[]>
) {
    // get the operators!
    let key = process.env.API_KEY;
    let base_url = process.env.BASE_URL;
    let api_path = process.env.API_PATH;

    let stops: Stop[] = [];

    let { operator_id } = req.query;

    if (operator_id instanceof Array) operator_id = operator_id[0]


    try {
        let url = new URL(api_path + '/stops',base_url);
        url.searchParams.append("api_key", key!)
        url.searchParams.append("operator_id", operator_id!)
        url.searchParams.append("format", "json")

        const response = await axios.get(url);
        for (let o of response.data.Contents.dataObjects.ScheduledStopPoint) {
            stops.push({
                name: o.Name,
                id: o.id,
                extensions: {
                    type: Number(o.Extensions.LocationType),
                    parentStationId: o.Extensions.ParentStation,
                } as StopExtension,
            } as Stop);
        }
    } catch (error) {
        res.status(500);
        return;
    }

    res.status(200).json(stops)
}